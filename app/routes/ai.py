import asyncio
from typing import Any

import ollama
from fastapi import APIRouter, HTTPException, Query, WebSocket
from pydantic import BaseModel, Field
from starlette.websockets import WebSocketDisconnect

from app.services.ai_chat_hub import hub
from app.services.ai_service import analyze_log, chat_reply
from app.services.chat_history_service import get_messages_for_project, save_project_history
from app.services.ollama_config import OllamaPrefs, load_ollama_prefs, ollama_prefs_as_api_dict, save_ollama_prefs
from app.services.ollama_runtime import get_ollama_status_async, reset_ollama_base_url_cache, resolve_ollama_base_url_sync
from app.services.rag_service import rag_status, retrieve

router = APIRouter(prefix="/ai")


class AIRequest(BaseModel):
    log: str


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    history: list[ChatMessage] = Field(default_factory=list)


class OllamaConfigPut(BaseModel):
    base_url: str
    model: str
    timeout_seconds: int = Field(default=300, ge=10, le=7200)
    auto_start: bool = True
    container_name: str = ""
    host_start_command: str = ""
    ready_timeout_seconds: int = Field(default=60, ge=5, le=600)
    chat_max_tokens: int = Field(
        default=-1,
        ge=-1,
        le=262144,
        description="Ollama num_predict; -1 = baglam dolana kadar (dusunce+yanit ortak)",
    )


class ChatHistoryBody(BaseModel):
    project_id: str = Field(min_length=1, max_length=512)
    messages: list[dict[str, Any]] = Field(default_factory=list)


class RagSearchRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=50)


def _ollama_client() -> tuple[ollama.Client, OllamaPrefs]:
    prefs = load_ollama_prefs()
    base = resolve_ollama_base_url_sync(prefs) or prefs.base_url.rstrip("/")
    timeout = min(max(prefs.timeout_seconds, 5), 600)
    return ollama.Client(host=base, timeout=timeout), prefs


def _ollama_list_models_sync() -> list[str]:
    client, _prefs = _ollama_client()
    lr = client.list()
    raw = lr["models"] if isinstance(lr, dict) else getattr(lr, "models", []) or []
    names: list[str] = []
    for item in raw:
        if isinstance(item, dict):
            n = item.get("model") or item.get("name")
        else:
            n = getattr(item, "model", None) or getattr(item, "name", None)
        if isinstance(n, str) and n.strip():
            names.append(n.strip())
    return names


def _ollama_ps_sync() -> dict[str, Any]:
    client, _prefs = _ollama_client()
    pr = client.ps()
    if isinstance(pr, dict):
        return pr
    return {"models": getattr(pr, "models", [])}


@router.get("/status")
async def ai_status():
    return await get_ollama_status_async()


@router.get("/ollama/config")
async def ollama_config_get():
    return ollama_prefs_as_api_dict(load_ollama_prefs())


@router.put("/ollama/config")
async def ollama_config_put(body: OllamaConfigPut):
    prefs = OllamaPrefs(
        base_url=body.base_url.strip() or "http://127.0.0.1:11434",
        model=body.model.strip() or "hf.co/bartowski/Qwen_Qwen3.6-27B-GGUF:IQ3_XS",
        timeout_seconds=body.timeout_seconds,
        auto_start=body.auto_start,
        container_name=body.container_name.strip(),
        host_start_command=body.host_start_command.strip(),
        ready_timeout_seconds=body.ready_timeout_seconds,
        chat_max_tokens=body.chat_max_tokens,
    )
    save_ollama_prefs(prefs)
    reset_ollama_base_url_cache()
    return ollama_prefs_as_api_dict(prefs)


@router.get("/ollama/models")
async def ollama_models_list():
    try:
        names = await asyncio.to_thread(_ollama_list_models_sync)
        return {"models": names}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Ollama model listesi alinamadi: {exc}") from exc


@router.get("/ollama/ps")
async def ollama_ps():
    try:
        return await asyncio.to_thread(_ollama_ps_sync)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Ollama ps alinamadi: {exc}") from exc


@router.get("/rag/status")
async def rag_status_get():
    return await asyncio.to_thread(rag_status)


@router.post("/rag/search")
async def rag_search(request: RagSearchRequest):
    hits = await asyncio.to_thread(retrieve, request.query, request.top_k)
    return {
        "count": len(hits),
        "results": [
            {
                "file_path": hit.file_path,
                "category": hit.category,
                "score": hit.score,
                "content": hit.content,
            }
            for hit in hits
        ],
    }


@router.get("/chat/history")
async def chat_history_get(project_id: str = Query(..., min_length=1, max_length=512)):
    return {"messages": get_messages_for_project(project_id)}


@router.put("/chat/history")
async def chat_history_put(body: ChatHistoryBody):
    save_project_history(body.project_id, body.messages)
    return {"ok": True}


@router.post("/analyze")
async def analyze(request: AIRequest):
    result = await asyncio.to_thread(analyze_log, request.log)
    return {"analysis": result}


@router.post("/chat")
async def chat(request: ChatRequest):
    result = await asyncio.to_thread(
        chat_reply,
        request.message,
        [{"role": item.role, "content": item.content} for item in request.history],
    )
    out: dict[str, object] = {"reply": result.text}
    if result.thinking:
        out["thinking"] = result.thinking
    return out


@router.websocket("/chat/ws")
async def chat_websocket(websocket: WebSocket):
    await hub.connect(websocket)
    try:
        while True:
            payload = await websocket.receive_json()
            if not isinstance(payload, dict):
                await hub.handle_message(
                    websocket,
                    {"type": "error", "message": "invalid payload"},
                )
                continue
            await hub.handle_message(websocket, payload)
    except WebSocketDisconnect:
        await hub.disconnect(websocket)

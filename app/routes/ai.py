from fastapi import APIRouter, WebSocket
from pydantic import BaseModel, Field
from starlette.websockets import WebSocketDisconnect

from app.services.ai_chat_hub import hub
from app.services.ai_service import analyze_log, chat_reply
from app.services.ollama_runtime import get_ollama_status

router = APIRouter(prefix="/ai")


class AIRequest(BaseModel):
    log: str


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    history: list[ChatMessage] = Field(default_factory=list)


@router.get("/status")
def ai_status():
    return get_ollama_status()


@router.post("/analyze")
def analyze(request: AIRequest):
    result = analyze_log(request.log)
    return {"analysis": result}


@router.post("/chat")
def chat(request: ChatRequest):
    result = chat_reply(
        request.message,
        [{"role": item.role, "content": item.content} for item in request.history],
    )
    return {"reply": result}


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

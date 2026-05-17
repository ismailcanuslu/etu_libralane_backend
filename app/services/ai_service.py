from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

import httpx
import ollama

from app.services.ollama_config import OllamaPrefs, load_ollama_prefs
from app.services.ollama_runtime import ensure_ollama_running, resolve_ollama_base_url_sync
from app.services.text_format import (
    DEFAULT_CHAT_MAX_TOKENS,
    merge_stream_field,
    normalize_model_markdown,
)

ChatMode = str  # "agent" | "plan"

_BASE_SYSTEM = (
    "You are an ASIC EDA assistant for LibreLane/OpenLane RTL-to-GDS flows. "
    "Answer in Turkish when the user writes in Turkish. "
    "Always format replies in valid Markdown: use blank lines between paragraphs, "
    "## headings for sections, numbered or bullet lists for steps, and fenced ```code``` blocks for Verilog/config. "
    "Never glue words together without spaces."
)

_MODE_PROMPTS: dict[str, str] = {
    "agent": (
        "Mode: AGENT. Answer directly and help execute the user's design task. "
        "Be concise; include code or file paths when relevant. "
        "When proposing file edits, use this exact format for each file (full file content, not a patch):\n"
        "**Dosya:** `relative/path/from/project/root`\n"
        "```verilog\n"
        "<full file content>\n"
        "```\n"
        "The IDE shows a red/green diff and waits for user approval before writing to disk. "
        "Do not claim files were saved until the user approves."
    ),
    "plan": (
        "Mode: PLAN. Do not claim you ran tools or changed files. "
        "Produce a clear step-by-step plan in Markdown before any implementation detail. "
        "Structure: **Hedef**, **Adımlar** (numbered list), **Riskler**, **Sonraki aksiyon**. "
        "The IDE will save your reply under plans/ for user review and approval. "
        "Wait for user confirmation before describing execution."
    ),
}


def _system_prompt(mode: str | None) -> str:
    key = (mode or "agent").strip().lower()
    extra = _MODE_PROMPTS.get(key, _MODE_PROMPTS["agent"])
    return f"{_BASE_SYSTEM}\n\n{extra}"


@dataclass(frozen=True)
class ChatReply:
    """Ollama /api/chat yaniti — bazi modeller metni `thinking` altinda verir."""

    text: str
    thinking: str | None = None


def _message_dict_from_response(response: object) -> dict[str, Any] | None:
    if isinstance(response, dict):
        m = response.get("message")
        return m if isinstance(m, dict) else None
    m = getattr(response, "message", None)
    return m if isinstance(m, dict) else None


def _stringify_thinking_fragment(val: Any) -> str | None:
    if isinstance(val, str) and val.strip():
        return val.strip()
    if isinstance(val, list):
        parts: list[str] = []
        for item in val:
            if isinstance(item, str) and item.strip():
                parts.append(item.strip())
            elif isinstance(item, dict):
                t = item.get("thinking") or item.get("text") or item.get("content")
                s = _stringify_thinking_fragment(t)
                if s:
                    parts.append(s)
        return "\n".join(parts).strip() if parts else None
    return None


def _extract_thinking_from_content_list(items: list[Any]) -> str | None:
    parts: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        typ = str(item.get("type") or "").lower()
        if typ in ("thinking", "reasoning"):
            s = _stringify_thinking_fragment(item.get("thinking") or item.get("text") or item.get("content"))
            if s:
                parts.append(s)
    return "\n\n".join(parts).strip() if parts else None


def _extract_thinking(msg: dict[str, Any]) -> str | None:
    for key in ("thinking", "reasoning", "reasoning_content"):
        val = msg.get(key)
        s = _stringify_thinking_fragment(val)
        if s:
            return s
    c = msg.get("content")
    if isinstance(c, list):
        nested = _extract_thinking_from_content_list(c)
        if nested:
            return nested
    return None


def _extract_content(msg: dict[str, Any], *, for_stream: bool = False) -> str:
    c = msg.get("content")
    parts: list[str] = []
    if isinstance(c, str):
        if for_stream:
            if c:
                parts.append(c)
        elif c.strip():
            parts.append(c.strip())
    elif isinstance(c, list):
        for item in c:
            if isinstance(item, dict):
                typ = str(item.get("type") or "").lower()
                if typ in ("thinking", "reasoning"):
                    continue
                if item.get("type") == "text" and isinstance(item.get("text"), str):
                    text = item["text"]
                    if for_stream:
                        if text:
                            parts.append(text)
                    elif text.strip():
                        parts.append(text.strip())
                elif isinstance(item.get("content"), str):
                    text = item["content"]
                    if for_stream:
                        if text:
                            parts.append(text)
                    elif text.strip():
                        parts.append(text.strip())
            elif isinstance(item, str):
                if for_stream:
                    if item:
                        parts.append(item)
                elif item.strip():
                    parts.append(item.strip())
    joined = "".join(parts) if for_stream else "\n".join(x for x in parts if x)
    return joined if for_stream else joined.strip()


def _normalize_chat_response(response: object) -> ChatReply:
    root_thinking: str | None = None
    if isinstance(response, dict):
        root_thinking = _stringify_thinking_fragment(response.get("thinking"))
    else:
        rt = getattr(response, "thinking", None)
        root_thinking = _stringify_thinking_fragment(rt)

    msg = _message_dict_from_response(response)
    if msg is None:
        return ChatReply(text="Ollama bos yanit dondurdu (message yok).", thinking=root_thinking)

    thinking = _extract_thinking(msg) or root_thinking
    content = _extract_content(msg)

    if content:
        return ChatReply(text=content, thinking=thinking)

    if thinking:
        return ChatReply(text="", thinking=thinking)

    return ChatReply(text="Ollama bos yanit dondurdu (icerik yok).", thinking=None)


def _ollama_chat(messages: list[dict[str, str]], *, max_tokens: int) -> ChatReply:
    ensure_ollama_running()
    prefs = load_ollama_prefs()
    base_url = resolve_ollama_base_url_sync(prefs) or prefs.base_url.rstrip("/")
    client = ollama.Client(host=base_url, timeout=prefs.timeout_seconds)
    chat_kwargs: dict[str, Any] = {
        "model": prefs.model,
        "messages": messages,
        "stream": False,
        "options": {"num_predict": max_tokens},
        # Ollama: ayri `message.thinking` icin gerekli (docs.ollama.com /api/chat `think`)
        "think": True,
    }
    try:
        response = client.chat(**chat_kwargs)
    except TypeError:
        chat_kwargs.pop("think", None)
        try:
            response = client.chat(**chat_kwargs)
        except Exception as exc:  # noqa: BLE001
            return ChatReply(text=f"Ollama API hatasi: {exc}", thinking=None)
    except Exception as exc:  # noqa: BLE001
        return ChatReply(text=f"Ollama API hatasi: {exc}", thinking=None)

    return _normalize_chat_response(response)


def analyze_log(log_text: str) -> str:
    messages = [
        {"role": "system", "content": _system_prompt("agent")},
        {
            "role": "user",
            "content": (
                "Analyze this EDA tool log.\n\n"
                "Return:\n"
                "- summary\n"
                "- success or fail\n"
                "- possible reason\n"
                "- next step\n\n"
                f"Log:\n{log_text}"
            ),
        },
    ]
    r = _ollama_chat(messages, max_tokens=600)
    if r.text.strip():
        return r.text.strip()
    if r.thinking:
        return r.thinking.strip()
    return "Ollama bos yanit dondurdu."


def resolve_chat_max_tokens(prefs: OllamaPrefs | None = None) -> int:
    """Ollama num_predict — dusunce ve yanit ayni kotadan uretilir."""
    prefs = prefs or load_ollama_prefs()
    try:
        n = int(prefs.chat_max_tokens)
    except (TypeError, ValueError):
        return DEFAULT_CHAT_MAX_TOKENS
    if n == 0:
        return DEFAULT_CHAT_MAX_TOKENS
    return n


def build_chat_messages(
    message: str,
    history: Iterable[Mapping[str, str]] | None = None,
    *,
    mode: str | None = None,
) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = [{"role": "system", "content": _system_prompt(mode)}]
    for item in history or ():
        role = item.get("role")
        content = item.get("content")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": message})
    return messages


async def aiter_chat_stream(
    message: str,
    history: Iterable[Mapping[str, str]] | None = None,
    *,
    max_tokens: int | None = None,
    mode: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Ollama /api/chat NDJSON akisi; her satirda birikimli thinking/content (varsa) dondurur."""
    messages = build_chat_messages(message, history, mode=mode)
    ensure_ollama_running()
    prefs = load_ollama_prefs()
    num_predict = resolve_chat_max_tokens(prefs) if max_tokens is None else max_tokens
    base_url = resolve_ollama_base_url_sync(prefs) or prefs.base_url.rstrip("/")
    url = f"{base_url}/api/chat"
    timeout = httpx.Timeout(prefs.timeout_seconds, connect=30.0)

    async def consume_body(body: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
        thinking_acc = ""
        content_acc = ""
        last_sig = ("", "")
        async with httpx.AsyncClient(timeout=timeout) as http:
            async with http.stream("POST", url, json=body) as resp:
                resp.raise_for_status()
                buf = b""
                async for bchunk in resp.aiter_bytes():
                    buf += bchunk
                    while b"\n" in buf:
                        raw_line, buf = buf.split(b"\n", 1)
                        line = raw_line.strip()
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        msg = data.get("message")
                        if isinstance(msg, dict):
                            th = msg.get("thinking")
                            if isinstance(th, str) and th.strip():
                                thinking_acc = merge_stream_field(thinking_acc, th)
                            ctext = _extract_content(msg, for_stream=True)
                            if ctext:
                                content_acc = merge_stream_field(content_acc, ctext)
                            elif isinstance(msg.get("content"), str) and msg["content"]:
                                content_acc = merge_stream_field(content_acc, msg["content"])
                        sig = (thinking_acc, content_acc)
                        done = bool(data.get("done"))
                        if sig == last_sig and not done:
                            continue
                        last_sig = sig
                        out: dict[str, Any] = {}
                        th_norm = normalize_model_markdown(thinking_acc)
                        co_norm = normalize_model_markdown(content_acc)
                        if th_norm:
                            out["thinking"] = th_norm
                        if co_norm:
                            out["content"] = co_norm
                        if out or done:
                            yield out

    base_body: dict[str, Any] = {
        "model": prefs.model,
        "messages": messages,
        "stream": True,
        "options": {"num_predict": num_predict},
    }
    with_think = {**base_body, "think": True}
    try:
        async for part in consume_body(with_think):
            yield part
        return
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code != 400:
            raise
    without_think = dict(base_body)
    async for part in consume_body(without_think):
        yield part


def chat_reply(
    message: str,
    history: Iterable[Mapping[str, str]] | None = None,
    *,
    mode: str | None = None,
) -> ChatReply:
    messages = build_chat_messages(message, history, mode=mode)
    result = _ollama_chat(messages, max_tokens=resolve_chat_max_tokens())
    return ChatReply(
        text=normalize_model_markdown(result.text) or "",
        thinking=normalize_model_markdown(result.thinking),
    )

from __future__ import annotations

from typing import Iterable, Mapping

import httpx

from app.core.config import get_settings

_settings = get_settings()
_SYSTEM_PROMPT = (
    "You are an ASIC EDA assistant for LibreLane/OpenLane RTL-to-GDS flows. "
    "Answer concisely in Turkish when the user writes in Turkish."
)


def _ollama_chat(messages: list[dict[str, str]], *, max_tokens: int) -> str:
    payload = {
        "model": _settings.ollama_model,
        "messages": messages,
        "stream": False,
        "options": {"num_predict": max_tokens},
    }
    url = f"{_settings.ollama_base_url.rstrip('/')}/api/chat"
    try:
        with httpx.Client(timeout=_settings.ollama_timeout_seconds) as client:
            response = client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as exc:
        return f"Ollama API hatasi: {exc}"

    message = data.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()

    return "Ollama bos yanit dondurdu."


def analyze_log(log_text: str) -> str:
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
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
    return _ollama_chat(messages, max_tokens=600)


def chat_reply(message: str, history: Iterable[Mapping[str, str]] | None = None) -> str:
    messages: list[dict[str, str]] = [{"role": "system", "content": _SYSTEM_PROMPT}]
    for item in history or ():
        role = item.get("role")
        content = item.get("content")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": message})
    return _ollama_chat(messages, max_tokens=900)

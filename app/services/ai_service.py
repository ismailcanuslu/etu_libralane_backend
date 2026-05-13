from __future__ import annotations

from typing import Iterable, Mapping

import ollama

from app.services.ollama_config import load_ollama_prefs
from app.services.ollama_runtime import ensure_ollama_running, resolve_ollama_base_url_sync

_SYSTEM_PROMPT = (
    "You are an ASIC EDA assistant for LibreLane/OpenLane RTL-to-GDS flows. "
    "Answer concisely in Turkish when the user writes in Turkish."
)


def _ollama_chat(messages: list[dict[str, str]], *, max_tokens: int) -> str:
    ensure_ollama_running()
    prefs = load_ollama_prefs()
    base_url = resolve_ollama_base_url_sync(prefs) or prefs.base_url.rstrip("/")
    client = ollama.Client(host=base_url, timeout=prefs.timeout_seconds)
    try:
        response = client.chat(
            model=prefs.model,
            messages=messages,
            stream=False,
            options={"num_predict": max_tokens},
        )
    except Exception as exc:  # noqa: BLE001
        return f"Ollama API hatasi: {exc}"

    message = response.get("message") if isinstance(response, dict) else getattr(response, "message", None)
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

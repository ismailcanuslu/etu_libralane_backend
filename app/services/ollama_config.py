"""Ollama ayarlari — yalnizca JSON dosyasindan (env / .env yok)."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

from app.core.config import get_settings


@dataclass
class OllamaPrefs:
    base_url: str = "http://127.0.0.1:11434"
    model: str = "gemma4:26b"
    timeout_seconds: int = 300
    auto_start: bool = True
    container_name: str = ""
    host_start_command: str = ""
    ready_timeout_seconds: int = 60
    # Ollama num_predict: dusunce + yanit ortak; -1 = baglam dolana kadar
    chat_max_tokens: int = -1


def _prefs_file_path() -> Path:
    db = Path(get_settings().db_path).expanduser().resolve()
    parent = db.parent
    if not parent.name:
        parent = Path.cwd()
    return parent / "ollama_prefs.json"


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _defaults_dict() -> dict[str, Any]:
    return {f.name: getattr(OllamaPrefs(), f.name) for f in fields(OllamaPrefs)}


def load_ollama_prefs() -> OllamaPrefs:
    path = _prefs_file_path()
    if not path.is_file():
        return OllamaPrefs()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return OllamaPrefs()
    if not isinstance(raw, dict):
        return OllamaPrefs()
    base = _defaults_dict()
    for key in base:
        if key in raw:
            base[key] = raw[key]
    try:
        chat_max = int(base.get("chat_max_tokens", OllamaPrefs.chat_max_tokens))
        return OllamaPrefs(
            base_url=str(base["base_url"]).strip() or OllamaPrefs.base_url,
            model=str(base["model"]).strip() or OllamaPrefs.model,
            timeout_seconds=int(base["timeout_seconds"]),
            auto_start=bool(base["auto_start"]),
            container_name=str(base["container_name"] or ""),
            host_start_command=str(base["host_start_command"] or ""),
            ready_timeout_seconds=int(base["ready_timeout_seconds"]),
            chat_max_tokens=chat_max,
        )
    except (TypeError, ValueError):
        return OllamaPrefs()


def save_ollama_prefs(prefs: OllamaPrefs) -> None:
    path = _prefs_file_path()
    _ensure_parent(path)
    data = asdict(prefs)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def merge_and_save_ollama_prefs(updates: dict[str, Any]) -> OllamaPrefs:
    current = load_ollama_prefs()
    d = asdict(current)
    field_names = {f.name for f in fields(OllamaPrefs)}
    for k, v in updates.items():
        if k in field_names:
            d[k] = v
    merged = OllamaPrefs(
        base_url=str(d["base_url"]).strip() or OllamaPrefs.base_url,
        model=str(d["model"]).strip() or OllamaPrefs.model,
        timeout_seconds=int(d["timeout_seconds"]),
        auto_start=bool(d["auto_start"]),
        container_name=str(d["container_name"] or ""),
        host_start_command=str(d["host_start_command"] or ""),
        ready_timeout_seconds=int(d["ready_timeout_seconds"]),
        chat_max_tokens=int(d.get("chat_max_tokens", OllamaPrefs.chat_max_tokens)),
    )
    save_ollama_prefs(merged)
    return merged


def ollama_prefs_as_api_dict(prefs: OllamaPrefs) -> dict[str, Any]:
    return asdict(prefs)

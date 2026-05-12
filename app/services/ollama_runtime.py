from __future__ import annotations

import subprocess
import time

import docker
import httpx
from docker.errors import APIError, NotFound

from app.core.config import get_settings


def _tags_url() -> str:
    settings = get_settings()
    return f"{settings.ollama_base_url.rstrip('/')}/api/tags"


def _ollama_ready(timeout_seconds: float) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with httpx.Client(timeout=3) as client:
                response = client.get(_tags_url())
                if response.status_code == 200:
                    return True
        except httpx.HTTPError:
            pass
        time.sleep(1)
    return False


def _start_host_ollama(command: str) -> bool:
    try:
        completed = subprocess.run(
            command,
            shell=True,
            check=False,
            timeout=30,
            capture_output=True,
            text=True,
        )
    except subprocess.TimeoutExpired:
        return False
    return completed.returncode == 0


def _start_ollama_container(container_name: str) -> bool:
    try:
        container = docker.from_env().containers.get(container_name)
    except NotFound:
        return False
    except APIError:
        return False

    try:
        container.reload()
        if container.status != "running":
            container.start()
    except APIError:
        return False
    return True


def ensure_ollama_running() -> None:
    settings = get_settings()
    if _ollama_ready(2):
        return
    if not settings.ollama_auto_start:
        return

    host_command = settings.ollama_host_start_command.strip()
    if host_command:
        _start_host_ollama(host_command)

    container_name = settings.ollama_container_name.strip()
    if container_name:
        _start_ollama_container(container_name)

    _ollama_ready(float(settings.ollama_ready_timeout_seconds))


def get_ollama_status() -> dict[str, object]:
    settings = get_settings()
    model = settings.ollama_model
    base_url = settings.ollama_base_url.rstrip("/")

    if settings.ollama_auto_start:
        ensure_ollama_running()

    try:
        with httpx.Client(timeout=5) as client:
            response = client.get(_tags_url())
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPError as exc:
        return {
            "ready": False,
            "model": model,
            "message": (
                f"Ollama erisilemedi ({base_url}): {exc}. "
                "Host'ta systemctl status ollama ve model pull kontrol edin; "
                "container'dan erisim icin OLLAMA_HOST=0.0.0.0:11434 gerekebilir."
            ),
            "ollama_base_url": base_url,
        }

    models: list[str] = []
    for item in payload.get("models", []):
        if isinstance(item, dict):
            name = item.get("name")
            if isinstance(name, str) and name:
                models.append(name)

    model_ready = any(
        name == model or name.startswith(f"{model}:") or model.startswith(f"{name}:")
        for name in models
    )
    if model_ready:
        message = f"Ollama hazir — {model}"
        ready = True
    elif models:
        message = f"Ollama acik ancak {model} modeli bulunamadi."
        ready = False
    else:
        message = "Ollama acik ancak yuklu model listesi bos."
        ready = False

    return {
        "ready": ready,
        "model": model,
        "message": message,
        "ollama_base_url": base_url,
        "models": models,
    }

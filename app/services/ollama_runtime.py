from __future__ import annotations

import asyncio
import shlex
import subprocess
import time

import docker
import httpx
from docker.errors import APIError, NotFound

from app.core.config import Settings, get_settings

_resolved_ollama_base_url: str | None = None


def _candidate_ollama_base_urls(settings: Settings) -> list[str]:
    urls: list[str] = []
    primary = settings.ollama_base_url.rstrip("/")
    if primary:
        urls.append(primary)
    for candidate in (
        "http://127.0.0.1:11434",
        "http://localhost:11434",
        "http://host.docker.internal:11434",
    ):
        if candidate not in urls:
            urls.append(candidate)
    return urls


def _tags_url_for(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/api/tags"


def _tags_url() -> str:
    settings = get_settings()
    base = _resolved_ollama_base_url or settings.ollama_base_url.rstrip("/")
    return _tags_url_for(base)


def build_ollama_host_start_command(settings: Settings | None = None) -> str:
    """Host'ta Ollama'yi baslatmak icin nsenter komutu.

    Ozel OLLAMA_HOST_START_COMMAND verilmediyse `ollama run <model>` arka planda calisir.
    """
    settings = settings or get_settings()
    custom = settings.ollama_host_start_command.strip()
    if custom:
        return custom

    model = shlex.quote(settings.ollama_model)
    return (
        "nsenter -t 1 -m -u -n -i -p -F -- sh -lc "
        f"'command -v ollama >/dev/null 2>&1 || exit 127; "
        f"nohup ollama run {model} </dev/null >>/tmp/ollama-run.log 2>&1 &'"
    )


def _probe_tags_sync(client: httpx.Client, base_url: str) -> bool:
    try:
        response = client.get(_tags_url_for(base_url))
        return response.status_code == 200
    except httpx.HTTPError:
        return False


async def _probe_tags_async(client: httpx.AsyncClient, base_url: str) -> bool:
    try:
        response = await client.get(_tags_url_for(base_url))
        return response.status_code == 200
    except httpx.HTTPError:
        return False


def resolve_ollama_base_url_sync(settings: Settings | None = None) -> str | None:
    global _resolved_ollama_base_url
    settings = settings or get_settings()
    if _resolved_ollama_base_url:
        return _resolved_ollama_base_url
    with httpx.Client(timeout=3) as client:
        for base_url in _candidate_ollama_base_urls(settings):
            if _probe_tags_sync(client, base_url):
                _resolved_ollama_base_url = base_url
                return base_url
    return None


async def resolve_ollama_base_url_async(settings: Settings | None = None) -> str | None:
    global _resolved_ollama_base_url
    settings = settings or get_settings()
    if _resolved_ollama_base_url:
        return _resolved_ollama_base_url
    async with httpx.AsyncClient(timeout=3) as client:
        for base_url in _candidate_ollama_base_urls(settings):
            if await _probe_tags_async(client, base_url):
                _resolved_ollama_base_url = base_url
                return base_url
    return None


def _ollama_ready_sync(timeout_seconds: float) -> bool:
    settings = get_settings()
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if resolve_ollama_base_url_sync(settings):
            return True
        time.sleep(1)
    return False


async def _ollama_ready_async(timeout_seconds: float) -> bool:
    settings = get_settings()
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if await resolve_ollama_base_url_async(settings):
            return True
        await asyncio.sleep(1)
    return False


def _start_host_ollama(command: str) -> bool:
    try:
        subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError:
        return False
    return True


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


def _kick_start_ollama(settings: Settings) -> None:
    _start_host_ollama(build_ollama_host_start_command(settings))
    container_name = settings.ollama_container_name.strip()
    if container_name:
        _start_ollama_container(container_name)


def ensure_ollama_running() -> None:
    """Sohbet gibi uzun islemler icin Ollama hazir olana kadar bekler (senkron)."""
    settings = get_settings()
    if _ollama_ready_sync(2):
        return
    if not settings.ollama_auto_start:
        return

    _kick_start_ollama(settings)
    _ollama_ready_sync(float(settings.ollama_ready_timeout_seconds))


async def kick_start_ollama_async() -> None:
    settings = get_settings()
    if not settings.ollama_auto_start:
        return
    await asyncio.to_thread(_kick_start_ollama, settings)


def _serialize_status_payload(
    *,
    model: str,
    base_url: str,
    payload: dict[str, object],
) -> dict[str, object]:
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


async def _fetch_tags_payload_async(settings: Settings) -> tuple[str | None, dict[str, object] | None, str | None]:
    base_url = await resolve_ollama_base_url_async(settings)
    if base_url is None:
        return None, None, None
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(_tags_url_for(base_url))
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPError as exc:
        return base_url, None, str(exc)
    return base_url, payload, None


async def get_ollama_status_async() -> dict[str, object]:
    settings = get_settings()
    model = settings.ollama_model
    configured = settings.ollama_base_url.rstrip("/")

    if not await _ollama_ready_async(2):
        if settings.ollama_auto_start:
            await kick_start_ollama_async()
            await _ollama_ready_async(3)

    base_url, payload, error = await _fetch_tags_payload_async(settings)
    if error is not None:
        return {
            "ready": False,
            "model": model,
            "message": (
                f"Ollama erisilemedi ({base_url or configured}): {error}. "
                f"Host'ta `curl http://127.0.0.1:11434` calisiyorsa backend icin "
                "network_mode: host veya OLLAMA_HOST=0.0.0.0:11434 kullanin."
            ),
            "ollama_base_url": base_url or configured,
        }
    if payload is None:
        return {
            "ready": False,
            "model": model,
            "message": (
                "Ollama API'sine ulasilamadi. Host'ta servis acik olsa bile container "
                "127.0.0.1:11434 adresine erisemeyebilir; backend'i host aginda calistirin "
                "veya Ollama'yi 0.0.0.0:11434 dinleyecek sekilde acin."
            ),
            "ollama_base_url": configured,
        }

    return _serialize_status_payload(model=model, base_url=base_url or configured, payload=payload)


def get_ollama_status() -> dict[str, object]:
    """Senkron cagri noktalari icin kisa timeout ile durum okur."""
    settings = get_settings()
    model = settings.ollama_model
    configured = settings.ollama_base_url.rstrip("/")

    if not _ollama_ready_sync(2) and settings.ollama_auto_start:
        _kick_start_ollama(settings)
        _ollama_ready_sync(3)

    base_url = resolve_ollama_base_url_sync(settings)
    if base_url is None:
        return {
            "ready": False,
            "model": model,
            "message": (
                "Ollama API'sine ulasilamadi. Host'ta servis acik olsa bile container "
                "127.0.0.1:11434 adresine erisemeyebilir; backend'i host aginda calistirin "
                "veya Ollama'yi 0.0.0.0:11434 dinleyecek sekilde acin."
            ),
            "ollama_base_url": configured,
        }

    try:
        with httpx.Client(timeout=5) as client:
            response = client.get(_tags_url_for(base_url))
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPError as exc:
        return {
            "ready": False,
            "model": model,
            "message": (
                f"Ollama erisilemedi ({base_url}): {exc}. "
                f"Host'ta `curl http://127.0.0.1:11434` calisiyorsa backend icin "
                "network_mode: host veya OLLAMA_HOST=0.0.0.0:11434 kullanin."
            ),
            "ollama_base_url": base_url,
        }

    return _serialize_status_payload(model=model, base_url=base_url, payload=payload)

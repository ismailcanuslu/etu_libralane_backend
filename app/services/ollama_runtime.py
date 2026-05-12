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

"""Docker SDK ile per-job ephemeral runner container.

Backend container.sock üzerinden host docker'a bağlanır ve runner imajını
mount edilmiş bir workdir ile başlatır. stdout/stderr satır satır pipe edilir.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import AsyncIterator, Iterable, Optional

import docker
from docker.errors import APIError, ImageNotFound, NotFound

from app.core.config import get_settings


@dataclass
class RunResult:
    exit_code: int
    container_id: str


@dataclass
class LogLine:
    stream: str  # "stdout" | "stderr" | "system"
    line: str


def _client() -> docker.DockerClient:
    return docker.from_env()


def _ensure_image(image: str) -> None:
    cli = _client()
    try:
        cli.images.get(image)
    except ImageNotFound:
        try:
            cli.images.pull(image)
        except APIError:
            # Lokal build olabilir (örn. librelane/runner:basic). Yoksa container.run hata verecek.
            pass


def _ensure_network(network: Optional[str]) -> Optional[str]:
    """Runner agini olusturur; yoksa None (Docker varsayilan bridge)."""
    if not network:
        return None
    cli = _client()
    try:
        cli.networks.get(network)
        return network
    except NotFound:
        try:
            cli.networks.create(network, driver="bridge")
            return network
        except APIError:
            return None


def create_container(
    image: str,
    cmd: list[str],
    host_workdir: str,
    *,
    env: Optional[dict] = None,
    network: Optional[str] = None,
    extra_volumes: Optional[dict] = None,
):
    settings = get_settings()
    _ensure_image(image)
    cli = _client()
    volumes = {host_workdir: {"bind": settings.jobs_workdir_in_runner, "mode": "rw"}}
    if extra_volumes:
        volumes.update(extra_volumes)
    net = _ensure_network(network or settings.runner_network)
    create_kwargs: dict = {
        "image": image,
        "command": cmd,
        "working_dir": settings.jobs_workdir_in_runner,
        "environment": env or {},
        "volumes": volumes,
        "detach": True,
        "tty": False,
        "stdin_open": False,
        "labels": {"librelane.role": "runner"},
    }
    if net:
        create_kwargs["network"] = net
    container = cli.containers.create(**create_kwargs)
    return container


async def stream_container(container) -> AsyncIterator[LogLine]:
    """Container'dan stdout/stderr'i satır satır akıtır.

    Docker SDK blocking, bu yüzden okumayı thread'e atıp asyncio.Queue üzerinden
    iletiyoruz.
    """
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[Optional[LogLine]] = asyncio.Queue(maxsize=1024)

    def _reader():
        try:
            try:
                container.start()
            except APIError as e:
                loop.call_soon_threadsafe(queue.put_nowait, LogLine("system", f"start error: {e}"))
                loop.call_soon_threadsafe(queue.put_nowait, None)
                return

            try:
                # demux=True → (stdout_bytes, stderr_bytes)
                gen = container.attach(
                    stream=True,
                    logs=True,
                    stdout=True,
                    stderr=True,
                    demux=True,
                )
            except APIError as e:
                loop.call_soon_threadsafe(queue.put_nowait, LogLine("system", f"attach error: {e}"))
                loop.call_soon_threadsafe(queue.put_nowait, None)
                return

            stdout_buf = b""
            stderr_buf = b""
            for chunk in gen:
                if chunk is None:
                    continue
                stdout_chunk, stderr_chunk = chunk if isinstance(chunk, tuple) else (chunk, None)

                if stdout_chunk:
                    stdout_buf += stdout_chunk
                    while b"\n" in stdout_buf:
                        line, stdout_buf = stdout_buf.split(b"\n", 1)
                        loop.call_soon_threadsafe(
                            queue.put_nowait,
                            LogLine("stdout", line.decode("utf-8", "replace").rstrip("\r")),
                        )
                if stderr_chunk:
                    stderr_buf += stderr_chunk
                    while b"\n" in stderr_buf:
                        line, stderr_buf = stderr_buf.split(b"\n", 1)
                        loop.call_soon_threadsafe(
                            queue.put_nowait,
                            LogLine("stderr", line.decode("utf-8", "replace").rstrip("\r")),
                        )

            # Kalan tampon (newline'sız son parça)
            if stdout_buf:
                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    LogLine("stdout", stdout_buf.decode("utf-8", "replace").rstrip("\r")),
                )
            if stderr_buf:
                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    LogLine("stderr", stderr_buf.decode("utf-8", "replace").rstrip("\r")),
                )
        except Exception as e:  # noqa: BLE001
            loop.call_soon_threadsafe(queue.put_nowait, LogLine("system", f"reader exception: {e}"))
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    task = loop.run_in_executor(None, _reader)
    try:
        while True:
            item = await queue.get()
            if item is None:
                break
            yield item
    finally:
        # Reader executor'ı sonlanana kadar bekle (kuyruğa None koyması garanti)
        try:
            await task
        except Exception:
            pass


async def wait_container(container, timeout: Optional[int] = None) -> int:
    """Container'ın bitmesini bekler ve exit code döner."""
    loop = asyncio.get_running_loop()

    def _wait() -> int:
        try:
            result = container.wait(timeout=timeout) if timeout else container.wait()
            return int(result.get("StatusCode", -1))
        except APIError:
            return -1

    return await loop.run_in_executor(None, _wait)


def remove_container(container) -> None:
    try:
        container.remove(force=True)
    except (APIError, NotFound):
        pass


def interrupt_container_by_id(container_id: str, *, signal: str = "SIGINT") -> bool:
    """Container ana sürecine SIGINT (Ctrl+C) veya başka sinyal gönderir."""
    try:
        container = _client().containers.get(container_id)
        container.kill(signal=signal)
        return True
    except (APIError, NotFound):
        return False


def kill_container_by_id(container_id: str) -> bool:
    return interrupt_container_by_id(container_id, signal="SIGKILL")


def kill_all_runner_containers() -> list[str]:
    """Etiketli runner container'larina SIGINT gonderir ve kaldirir."""
    cli = _client()
    removed: list[str] = []
    for container in cli.containers.list(all=True, filters={"label": "librelane.role=runner"}):
        cid = container.id
        if not cid:
            continue
        try:
            container.kill(signal="SIGINT")
        except (APIError, NotFound):
            pass
        try:
            container.remove(force=True)
            removed.append(cid)
        except (APIError, NotFound):
            pass
    return removed

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
    container = cli.containers.create(
        image=image,
        command=cmd,
        working_dir=settings.jobs_workdir_in_runner,
        environment=env or {},
        volumes=volumes,
        network=network or settings.runner_network,
        detach=True,
        tty=False,
        stdin_open=False,
        labels={"librelane.role": "runner"},
        # network_mode'u network ile birlikte belirtemeyiz; create_host_config içinde network kullanır
    )
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


def kill_container_by_id(container_id: str) -> bool:
    try:
        container = _client().containers.get(container_id)
        container.kill()
        return True
    except (APIError, NotFound):
        return False

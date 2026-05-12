from __future__ import annotations

import asyncio
import errno
import fcntl
import os
import pty
import struct
import subprocess
import termios
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import uuid4

from app.core.config import get_settings


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _set_winsize(fd: int, rows: int, cols: int) -> None:
    winsize = struct.pack("HHHH", rows, cols, 0, 0)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)


@dataclass
class HostShellSession:
    session_id: str
    project_id: str
    cwd: str
    master_fd: int
    pid: int
    created_at: datetime = field(default_factory=_utcnow)
    closed_at: Optional[datetime] = None
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def resize(self, rows: int, cols: int) -> None:
        rows = max(2, min(rows, 200))
        cols = max(20, min(cols, 500))
        with self._lock:
            if self.closed_at is not None:
                return
            _set_winsize(self.master_fd, rows, cols)

    def write(self, data: bytes) -> None:
        with self._lock:
            if self.closed_at is not None:
                return
            try:
                os.write(self.master_fd, data)
            except OSError:
                self.closed_at = _utcnow()

    def read(self, size: int = 4096) -> bytes:
        with self._lock:
            if self.closed_at is not None:
                return b""
            try:
                return os.read(self.master_fd, size)
            except OSError as exc:
                if exc.errno in {errno.EIO, errno.EBADF}:
                    self.closed_at = _utcnow()
                    return b""
                raise

    def close(self) -> None:
        with self._lock:
            if self.closed_at is not None:
                return
            self.closed_at = _utcnow()
            try:
                os.close(self.master_fd)
            except OSError:
                pass
            try:
                os.kill(self.pid, 15)
            except OSError:
                pass


class HostShellRegistry:
    def __init__(self) -> None:
        self._sessions: Dict[str, HostShellSession] = {}
        self._lock = threading.Lock()

    def create(self, project_id: str) -> HostShellSession:
        settings = get_settings()
        if not settings.enable_host_terminal:
            raise RuntimeError("host terminal disabled")

        cwd = os.path.join(settings.workspace_root, project_id)
        os.makedirs(cwd, exist_ok=True)

        with self._lock:
            open_count = sum(1 for session in self._sessions.values() if session.closed_at is None)
            if open_count >= settings.max_host_terminal_sessions:
                raise RuntimeError("host terminal session limit reached")

        master_fd, slave_fd = pty.openpty()
        _set_winsize(master_fd, 24, 80)
        os.set_blocking(master_fd, False)

        env = os.environ.copy()
        env["TERM"] = "xterm-256color"
        env["COLORTERM"] = "truecolor"

        if settings.host_terminal_use_nsenter:
            shell = settings.host_terminal_shell
            cmd = [
                "nsenter",
                "-t",
                "1",
                "-m",
                "-u",
                "-n",
                "-i",
                "-p",
                "-F",
                "--wd",
                cwd,
                shell,
                "-l",
            ]
        else:
            cmd = [settings.host_terminal_shell, "-l"]

        try:
            proc = subprocess.Popen(
                cmd,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                cwd=cwd,
                env=env,
                start_new_session=True,
            )
        except OSError as exc:
            os.close(master_fd)
            os.close(slave_fd)
            raise RuntimeError(f"host shell start failed: {exc}") from exc
        finally:
            os.close(slave_fd)

        session = HostShellSession(
            session_id=uuid4().hex,
            project_id=project_id,
            cwd=cwd,
            master_fd=master_fd,
            pid=proc.pid,
        )
        with self._lock:
            self._sessions[session.session_id] = session
        return session

    def get(self, session_id: str) -> Optional[HostShellSession]:
        with self._lock:
            return self._sessions.get(session_id)

    def close(self, session_id: str) -> bool:
        with self._lock:
            session = self._sessions.get(session_id)
        if session is None:
            return False
        session.close()
        return True

    def list_open(self, project_id: Optional[str] = None) -> List[HostShellSession]:
        with self._lock:
            sessions = [session for session in self._sessions.values() if session.closed_at is None]
        if project_id:
            sessions = [session for session in sessions if session.project_id == project_id]
        return sorted(sessions, key=lambda session: session.created_at)


registry = HostShellRegistry()


async def relay_master_to_websocket(session: HostShellSession, websocket) -> None:
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[bytes | None] = asyncio.Queue()

    def _on_readable() -> None:
        if session.closed_at is not None:
            loop.call_soon_threadsafe(queue.put_nowait, None)
            return
        try:
            data = os.read(session.master_fd, 4096)
        except BlockingIOError:
            return
        except OSError:
            loop.call_soon_threadsafe(queue.put_nowait, None)
            return
        if not data:
            loop.call_soon_threadsafe(queue.put_nowait, None)
            return
        loop.call_soon_threadsafe(queue.put_nowait, data)

    loop.add_reader(session.master_fd, _on_readable)
    try:
        while True:
            data = await queue.get()
            if data is None:
                break
            await websocket.send_bytes(data)
    finally:
        loop.remove_reader(session.master_fd)


async def relay_websocket_to_master(session: HostShellSession, websocket) -> None:
    while True:
        message = await websocket.receive()
        if message["type"] == "websocket.disconnect":
            break
        if message["type"] != "websocket.receive":
            continue
        if message.get("bytes") is not None:
            session.write(message["bytes"])
            continue
        text = message.get("text")
        if not text:
            continue
        if text.startswith("{"):
            try:
                import json

                payload = json.loads(text)
            except json.JSONDecodeError:
                payload = None
            if isinstance(payload, dict) and payload.get("type") == "resize":
                session.resize(int(payload.get("rows", 24)), int(payload.get("cols", 80)))
                continue
        session.write(text.encode("utf-8"))


def host_terminal_status() -> dict:
    settings = get_settings()
    if not settings.enable_host_terminal:
        return {"available": False, "mode": "disabled", "max_sessions": settings.max_host_terminal_sessions}
    mode = "host" if settings.host_terminal_use_nsenter else "container"
    return {
        "available": True,
        "mode": mode,
        "shell": settings.host_terminal_shell,
        "max_sessions": settings.max_host_terminal_sessions,
        "open_sessions": len(registry.list_open()),
    }

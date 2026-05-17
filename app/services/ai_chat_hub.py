from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect, WebSocketState

from app.services.ai_service import aiter_chat_stream, chat_reply


@dataclass
class ChatDelivery:
    request_id: str
    status: str = "queued"
    reply: str | None = None
    thinking: str | None = None
    error: str | None = None


@dataclass
class AIChatHub:
    """Tek istemci için AI sohbet kanalı; kopunca bekleyen yanıtları saklar."""

    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _active: WebSocket | None = None
    _deliveries: dict[str, ChatDelivery] = field(default_factory=dict)

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            previous = self._active
            self._active = websocket
        if previous is not None and previous is not websocket:
            await self._close_socket(previous, code=4000, reason="replaced by new session")
        await self._send(websocket, {"type": "connected"})
        await self._flush_pending(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            if self._active is websocket:
                self._active = None

    async def handle_message(self, websocket: WebSocket, payload: dict[str, Any]) -> None:
        msg_type = payload.get("type")
        if msg_type == "ping":
            await self._send(websocket, {"type": "pong"})
            return
        if msg_type == "ack":
            request_id = payload.get("id")
            if isinstance(request_id, str):
                async with self._lock:
                    self._deliveries.pop(request_id, None)
            return
        if msg_type != "chat":
            await self._send(
                websocket,
                {"type": "error", "message": f"unknown message type: {msg_type}"},
            )
            return

        request_id = payload.get("id")
        message = payload.get("message")
        history = payload.get("history")
        mode = payload.get("mode")
        if not isinstance(request_id, str) or not request_id.strip():
            await self._send(websocket, {"type": "error", "message": "id is required"})
            return
        if not isinstance(message, str) or not message.strip():
            await self._send(
                websocket,
                {"type": "error", "id": request_id, "message": "message is required"},
            )
            return
        if history is not None and not isinstance(history, list):
            await self._send(
                websocket,
                {"type": "error", "id": request_id, "message": "history must be a list"},
            )
            return
        if mode is not None and not isinstance(mode, str):
            await self._send(
                websocket,
                {"type": "error", "id": request_id, "message": "mode must be a string"},
            )
            return

        normalized_history = history or []
        chat_mode = (mode.strip().lower() if isinstance(mode, str) and mode.strip() else "agent")
        if chat_mode not in ("agent", "plan"):
            chat_mode = "agent"
        async with self._lock:
            self._deliveries[request_id] = ChatDelivery(request_id=request_id, status="queued")
        await self._send(websocket, {"type": "status", "id": request_id, "status": "queued"})
        asyncio.create_task(
            self._process_chat(request_id, message.strip(), normalized_history, chat_mode)
        )

    async def _process_chat(
        self,
        request_id: str,
        message: str,
        history: list[Any],
        mode: str,
    ) -> None:
        async with self._lock:
            delivery = self._deliveries.get(request_id)
            if delivery is None:
                return
            delivery.status = "processing"
        await self._broadcast({"type": "status", "id": request_id, "status": "processing"})

        last_thinking: str | None = None
        last_reply = ""
        try:
            stream_ok = False
            async for part in aiter_chat_stream(message, history, mode=mode):
                stream_ok = True
                th = part.get("thinking")
                co = part.get("content")
                if isinstance(th, str) and th.strip():
                    last_thinking = th.strip()
                if isinstance(co, str) and co.strip():
                    last_reply = co.strip()
                payload: dict[str, Any] = {"type": "stream_partial", "id": request_id}
                if isinstance(th, str) and th.strip():
                    payload["thinking"] = th.strip()
                if isinstance(co, str) and co.strip():
                    payload["content"] = co.strip()
                if len(payload) > 2:
                    await self._broadcast(payload)
            if not stream_ok:
                raise RuntimeError("ollama stream empty")
            await self._finish(request_id, reply=last_reply, thinking=last_thinking)
        except Exception as exc:  # noqa: BLE001
            try:
                result = await asyncio.to_thread(chat_reply, message, history, mode=mode)
                await self._finish(request_id, reply=result.text, thinking=result.thinking)
            except Exception as fallback_exc:  # noqa: BLE001
                await self._finish(request_id, error=f"Akis: {exc}; yedek: {fallback_exc}")

    async def _finish(
        self,
        request_id: str,
        *,
        reply: str | None = None,
        thinking: str | None = None,
        error: str | None = None,
    ) -> None:
        async with self._lock:
            delivery = self._deliveries.get(request_id)
            if delivery is None:
                delivery = ChatDelivery(request_id=request_id)
                self._deliveries[request_id] = delivery
            delivery.status = "failed" if error else "done"
            delivery.reply = reply
            delivery.thinking = thinking
            delivery.error = error

        if error:
            await self._broadcast(
                {"type": "error", "id": request_id, "message": error, "replay": False},
            )
            return
        payload: dict[str, Any] = {
            "type": "reply",
            "id": request_id,
            "reply": reply or "",
            "replay": False,
        }
        if thinking:
            payload["thinking"] = thinking
        await self._broadcast(payload)

    async def _flush_pending(self, websocket: WebSocket) -> None:
        async with self._lock:
            pending = list(self._deliveries.values())
        for delivery in pending:
            if delivery.status in {"queued", "processing"}:
                await self._send(
                    websocket,
                    {"type": "status", "id": delivery.request_id, "status": delivery.status, "replay": True},
                )
                continue
            if delivery.error:
                await self._send(
                    websocket,
                    {
                        "type": "error",
                        "id": delivery.request_id,
                        "message": delivery.error,
                        "replay": True,
                    },
                )
                continue
            if delivery.reply is not None:
                p: dict[str, Any] = {
                    "type": "reply",
                    "id": delivery.request_id,
                    "reply": delivery.reply,
                    "replay": True,
                }
                if delivery.thinking:
                    p["thinking"] = delivery.thinking
                await self._send(websocket, p)

    async def _broadcast(self, payload: dict[str, Any]) -> None:
        async with self._lock:
            websocket = self._active
        if websocket is None:
            return
        await self._send(websocket, payload)

    async def _send(self, websocket: WebSocket, payload: dict[str, Any]) -> None:
        if websocket.client_state != WebSocketState.CONNECTED:
            return
        try:
            await websocket.send_json(payload)
        except (WebSocketDisconnect, RuntimeError):
            await self.disconnect(websocket)

    async def _close_socket(self, websocket: WebSocket, *, code: int, reason: str) -> None:
        if websocket.client_state != WebSocketState.CONNECTED:
            return
        try:
            await websocket.close(code=code, reason=reason)
        except (WebSocketDisconnect, RuntimeError):
            return


hub = AIChatHub()

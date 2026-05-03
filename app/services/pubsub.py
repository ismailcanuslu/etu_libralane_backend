"""Per-job in-memory pub/sub for live SSE streaming.

Her job için bir konu (topic) açılır. Birden fazla subscriber aynı job'a abone
olabilir. Geç bağlananlar ring buffer'dan replay alır, sonra canlı yayına geçer.
"""
from __future__ import annotations

import asyncio
import json
import time
from collections import deque
from dataclasses import dataclass, field
from typing import AsyncIterator, Deque, Dict, List, Optional


@dataclass
class JobEvent:
    """SSE'ye serialize edilen olay."""

    type: str  # "line" | "status" | "done" | "error"
    data: dict
    seq: int = 0
    ts: float = field(default_factory=time.time)

    def to_sse(self) -> dict:
        return {
            "event": self.type,
            "id": str(self.seq),
            "data": json.dumps(self.data, ensure_ascii=False),
        }


class _Topic:
    def __init__(self, ring_size: int = 1000) -> None:
        self._buffer: Deque[JobEvent] = deque(maxlen=ring_size)
        self._subscribers: List[asyncio.Queue[Optional[JobEvent]]] = []
        self._closed = False
        self._seq = 0
        self._lock = asyncio.Lock()

    async def publish(self, event_type: str, data: dict) -> None:
        async with self._lock:
            self._seq += 1
            event = JobEvent(type=event_type, data=data, seq=self._seq)
            self._buffer.append(event)
            for q in list(self._subscribers):
                try:
                    q.put_nowait(event)
                except asyncio.QueueFull:
                    pass

    async def close(self) -> None:
        async with self._lock:
            self._closed = True
            for q in list(self._subscribers):
                try:
                    q.put_nowait(None)
                except asyncio.QueueFull:
                    pass
            self._subscribers.clear()

    async def subscribe(self, after_seq: int = 0) -> AsyncIterator[JobEvent]:
        """Topic'e abone ol; ring buffer'dan after_seq'den büyük olayları replay et,
        sonra canlı yayına devam et."""
        q: asyncio.Queue[Optional[JobEvent]] = asyncio.Queue(maxsize=2048)
        async with self._lock:
            replay = [e for e in self._buffer if e.seq > after_seq]
            already_closed = self._closed
            if not already_closed:
                self._subscribers.append(q)

        for event in replay:
            yield event

        if already_closed:
            return

        try:
            while True:
                item = await q.get()
                if item is None:
                    break
                # Race koruması: replay sırasında gelmiş olabilir
                if item.seq <= after_seq:
                    continue
                yield item
        finally:
            async with self._lock:
                if q in self._subscribers:
                    self._subscribers.remove(q)


class JobBroker:
    def __init__(self) -> None:
        self._topics: Dict[str, _Topic] = {}
        self._lock = asyncio.Lock()

    async def topic(self, job_id: str) -> _Topic:
        async with self._lock:
            t = self._topics.get(job_id)
            if t is None:
                t = _Topic()
                self._topics[job_id] = t
            return t

    async def publish(self, job_id: str, event_type: str, data: dict) -> None:
        topic = await self.topic(job_id)
        await topic.publish(event_type, data)

    async def close(self, job_id: str) -> None:
        async with self._lock:
            t = self._topics.get(job_id)
        if t is not None:
            await t.close()

    async def drop(self, job_id: str) -> None:
        async with self._lock:
            self._topics.pop(job_id, None)

    async def subscribe(self, job_id: str, after_seq: int = 0) -> AsyncIterator[JobEvent]:
        topic = await self.topic(job_id)
        async for event in topic.subscribe(after_seq=after_seq):
            yield event

    def has_topic(self, job_id: str) -> bool:
        return job_id in self._topics


broker = JobBroker()

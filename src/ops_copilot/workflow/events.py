"""Session event bus — per-session queues feeding the SSE streams (ADR-0004).

Event contract: {"agent", "type", "message", optional "data", "ts", "latency_ms"}.
A None sentinel closes the stream exactly once.
"""
from __future__ import annotations

import asyncio
import time


class EventBus:
    def __init__(self) -> None:
        self._queues: dict[str, asyncio.Queue] = {}

    def create(self, session_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._queues[session_id] = q
        return q

    def get(self, session_id: str) -> asyncio.Queue | None:
        return self._queues.get(session_id)

    def exists(self, session_id: str) -> bool:
        return session_id in self._queues

    @property
    def active_count(self) -> int:
        return len(self._queues)

    async def emit(self, session_id: str, agent: str, event_type: str, message: str,
                   data: dict | None = None, latency_ms: float | None = None) -> None:
        q = self._queues.get(session_id)
        if not q:
            return
        payload: dict = {
            "agent": agent, "type": event_type, "message": message, "ts": time.time(),
        }
        if data is not None:
            payload["data"] = data
        if latency_ms is not None:
            payload["latency_ms"] = round(latency_ms, 1)
        await q.put(payload)

    async def close(self, session_id: str) -> None:
        """Send the stream_close sentinel and drop the queue. Idempotent."""
        q = self._queues.get(session_id)
        if q is not None:
            await q.put(None)

    def drop(self, session_id: str) -> None:
        self._queues.pop(session_id, None)


bus = EventBus()

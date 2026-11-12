"""Async execution robustness — task registry, rate limiter (ADR-0002/0010)."""
from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque

from ops_copilot.config import settings


class TaskRegistry:
    """Tracks one background task per session; spawn replaces; cancel kills."""

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task] = {}

    def spawn(self, session_id: str, coro) -> asyncio.Task:
        self.cancel(session_id)
        task = asyncio.create_task(coro)
        self._tasks[session_id] = task
        task.add_done_callback(lambda t: self._tasks.pop(session_id, None))
        return task

    def cancel(self, session_id: str) -> None:
        task = self._tasks.get(session_id)
        if task and not task.done():
            task.cancel()
        self._tasks.pop(session_id, None)

    @property
    def active_count(self) -> int:
        return len(self._tasks)


class RateLimiter:
    """Sliding-window limiter per client key."""

    def __init__(self, max_per_minute: int) -> None:
        self.max = max_per_minute
        self._hits: dict[str, deque] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        window = self._hits[key]
        while window and now - window[0] > 60:
            window.popleft()
        if len(window) >= self.max:
            return False
        window.append(now)
        return True


task_registry = TaskRegistry()
launch_limiter = RateLimiter(settings.launch_rate_limit_per_min)


class IdempotencyCache:
    """request_id → session_id, bounded, best-effort (process-local)."""

    def __init__(self, capacity: int = 256) -> None:
        self.capacity = capacity
        self._map: dict[str, str] = {}

    def get(self, request_id: str) -> str | None:
        return self._map.get(request_id)

    def set(self, request_id: str, session_id: str) -> None:
        if len(self._map) >= self.capacity:
            self._map.pop(next(iter(self._map)))
        self._map[request_id] = session_id


idempotency = IdempotencyCache()

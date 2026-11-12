"""In-process metrics registry — node latencies, LLM calls, counters (ADR-0002).

This complements LangSmith tracing with an always-available JSON snapshot at
GET /metrics. Process-local; resets on restart (single-process deployment).
"""
from __future__ import annotations

import math
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class _Histogram:
    values: list[float] = field(default_factory=list)

    def record(self, v: float) -> None:
        # keep a bounded window (last 200 samples)
        self.values.append(v)
        if len(self.values) > 200:
            self.values = self.values[-200:]

    def stats(self) -> dict:
        if not self.values:
            return {"count": 0}
        vs = sorted(self.values)
        n = len(vs)

        def pct(p: float) -> float:
            idx = min(n - 1, max(0, math.ceil(p * n) - 1))
            return round(vs[idx], 1)

        return {
            "count": n,
            "avg_ms": round(sum(vs) / n, 1),
            "p50_ms": pct(0.50),
            "p95_ms": pct(0.95),
            "max_ms": round(vs[-1], 1),
        }


class MetricsRegistry:
    def __init__(self) -> None:
        self._nodes: dict[str, _Histogram] = defaultdict(_Histogram)
        self._llm: _Histogram = _Histogram()
        self._counters: dict[str, int] = defaultdict(int)
        self._lock = threading.Lock()

    def record_node(self, node: str, ms: float) -> None:
        with self._lock:
            self._nodes[node].record(ms)

    def record_llm(self, ms: float) -> None:
        with self._lock:
            self._llm.record(ms)

    def inc(self, counter: str, by: int = 1) -> None:
        with self._lock:
            self._counters[counter] += by

    class _Timer:
        def __init__(self, registry: MetricsRegistry, node: str, is_llm: bool):
            self._r, self._node, self._is_llm = registry, node, is_llm

        async def __aenter__(self):
            self._t0 = time.perf_counter()
            return self

        async def __aexit__(self, *exc):
            ms = (time.perf_counter() - self._t0) * 1000
            if self._is_llm:
                self._r.record_llm(ms)
            else:
                self._r.record_node(self._node, ms)
            return False

    def timer(self, node: str, llm: bool = False) -> _Timer:
        return MetricsRegistry._Timer(self, node, llm)

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "nodes": {k: h.stats() for k, h in sorted(self._nodes.items())},
                "llm_calls": self._llm.stats(),
                "counters": dict(sorted(self._counters.items())),
                "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }

    def reset(self) -> None:
        with self._lock:
            self._nodes.clear()
            self._llm = _Histogram()
            self._counters.clear()


metrics = MetricsRegistry()

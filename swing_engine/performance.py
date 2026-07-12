"""Performance measurement for swing detection."""

from __future__ import annotations

import time
import tracemalloc
from contextlib import contextmanager
from typing import Generator

from swing_engine.models import PerformanceMetrics


@contextmanager
def measure_performance(symbol: str, timeframe: str, version: str, bar_count: int) -> Generator[dict, None, None]:
    """Context manager tracking runtime, memory, and throughput."""
    tracemalloc.start()
    t0 = time.perf_counter()
    ctx: dict = {"swing_count": 0}

    try:
        yield ctx
    finally:
        elapsed = time.perf_counter() - t0
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        swings = ctx.get("swing_count", 0)
        ctx["metrics"] = PerformanceMetrics(
            symbol=symbol,
            timeframe=timeframe,
            version=version,
            runtime_ms=elapsed * 1000,
            bar_count=bar_count,
            swing_count=swings,
            bars_per_second=bar_count / elapsed if elapsed > 0 else 0,
            swings_per_second=swings / elapsed if elapsed > 0 else 0,
            peak_memory_mb=peak / (1024 * 1024),
        )

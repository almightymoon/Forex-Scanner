#!/usr/bin/env python3
"""Performance benchmark — bars/sec across symbols and timeframes."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared.types.models import Timeframe

from swing_engine import SwingEngine
from tests.swing_detection.fixtures import gold_candles, swing_candles, trend_candles

SYMBOLS = ["EURUSD", "GBPUSD", "XAUUSD", "USDJPY"]
TIMEFRAMES = [Timeframe.M5, Timeframe.M15, Timeframe.H1, Timeframe.H4]


def _bars(symbol: str, n: int, tf: Timeframe):
    if symbol == "XAUUSD":
        return gold_candles(n)
    return swing_candles(n, symbol=symbol, timeframe=tf)


def main() -> int:
    parser = argparse.ArgumentParser(description="Swing engine performance benchmark")
    parser.add_argument("--version", default="1.3.0")
    parser.add_argument("--bars", type=int, default=500)
    parser.add_argument("--symbols", nargs="*", default=SYMBOLS)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--output", type=Path, default=Path("benchmarks/reports/perf_benchmark.json"))
    args = parser.parse_args()

    engine = SwingEngine(version=args.version)
    results: list[dict] = []
    total_runs = 0
    total_ms = 0.0
    total_bars = 0

    for sym in args.symbols:
        for tf in TIMEFRAMES:
            bars = _bars(sym, args.bars, tf)
            for _ in range(args.warmup):
                engine.detect(bars[:50], symbol=sym, timeframe=tf)
            start = time.perf_counter()
            result = engine.detect(bars, symbol=sym, timeframe=tf)
            elapsed_ms = (time.perf_counter() - start) * 1000
            bps = len(bars) / (elapsed_ms / 1000) if elapsed_ms > 0 else 0
            mem = result.performance.peak_memory_mb if result.performance else 0
            results.append({
                "symbol": sym,
                "timeframe": tf.value,
                "bars": len(bars),
                "swings": len(result.swings),
                "runtime_ms": round(elapsed_ms, 2),
                "bars_per_second": round(bps, 1),
                "peak_memory_mb": mem,
            })
            total_runs += 1
            total_ms += elapsed_ms
            total_bars += len(bars)
            print(f"{sym} {tf.value}: {elapsed_ms:.1f}ms ({bps:.0f} bars/s)")

    summary = {
        "version": args.version,
        "total_runs": total_runs,
        "total_bars": total_bars,
        "total_ms": round(total_ms, 2),
        "avg_ms_per_run": round(total_ms / total_runs, 2) if total_runs else 0,
        "goal_100x8_under_1s": total_ms < 1000 if total_runs == 100 else None,
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nTotal: {total_runs} runs, {total_bars} bars, {total_ms:.0f}ms")
    print(f"Report: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

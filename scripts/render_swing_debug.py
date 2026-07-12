#!/usr/bin/env python3
"""Render interactive swing detection debug HTML."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared.types.models import Timeframe

from swing_engine import SwingEngine, SwingVisualizer, get_config
from tests.swing_detection.fixtures import gold_candles, range_candles, trend_candles, volatile_candles


def _bars(symbol: str, regime: str, n: int, tf: Timeframe):
    if symbol.upper().replace("/", "") == "XAUUSD":
        return gold_candles(n)
    if regime == "range":
        return range_candles(n, timeframe=tf)
    if regime == "volatile":
        return volatile_candles(n, timeframe=tf)
    return trend_candles(n, timeframe=tf)


def main() -> int:
    parser = argparse.ArgumentParser(description="Render swing detection debug HTML")
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--timeframe", default="H1")
    parser.add_argument("--bars", type=int, default=200)
    parser.add_argument("--regime", choices=["trend", "range", "volatile"], default="trend")
    parser.add_argument("--output", type=Path, default=Path("debug/swing_debug.html"))
    parser.add_argument("--version", default="1.3.0")
    args = parser.parse_args()

    tf = Timeframe(args.timeframe)
    bars = _bars(args.symbol, args.regime, args.bars, tf)
    cfg = get_config(tf, version=args.version, symbol=args.symbol)
    result = SwingEngine(cfg, version=args.version).detect(bars, symbol=args.symbol, timeframe=tf)
    path = SwingVisualizer().render_debug_html(result, bars, args.output)
    ms = result.performance.runtime_ms if result.performance else 0.0
    print(f"Wrote {path} ({len(result.swings)} swings, {ms:.1f}ms)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

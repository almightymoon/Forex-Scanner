#!/usr/bin/env python3
"""Render interactive swing detection debug HTML (optional structure overlays)."""

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
    parser.add_argument("--version", default="2.3.0")
    parser.add_argument("--csv", type=Path, default=None, help="Optional real OHLC CSV")
    parser.add_argument("--tail", type=int, default=400)
    parser.add_argument(
        "--with-structure",
        action="store_true",
        help="Overlay Market Structure v1 BOS/CHoCH + regime",
    )
    args = parser.parse_args()

    tf = Timeframe(args.timeframe)
    if args.csv:
        from scripts.smoke_structure_live_path import load_csv

        bars = load_csv(args.csv, args.symbol)
        if args.tail and args.tail > 0:
            bars = bars[-args.tail :]
    else:
        bars = _bars(args.symbol, args.regime, args.bars, tf)

    cfg = get_config(tf, version=args.version, symbol=args.symbol)
    result = SwingEngine(cfg, version=args.version).detect(
        bars, symbol=args.symbol, timeframe=tf
    )

    structure_events = None
    structure_context = None
    if args.with_structure:
        from services.quant_engine.market_structure import analyze_structure
        from services.quant_engine.market_structure.studio import structure_overlay_payload
        from services.quant_engine.swings.boundary import obtain_confirmed_swings

        swings = obtain_confirmed_swings(bars, version=args.version)
        snapshot = analyze_structure(bars, swings)
        overlay = structure_overlay_payload(snapshot)
        structure_events = overlay["structure_events"]
        structure_context = overlay["structure_context"]

    path = SwingVisualizer().render_debug_html(
        result,
        bars,
        args.output,
        structure_events=structure_events,
        structure_context=structure_context,
    )
    ms = result.performance.runtime_ms if result.performance else 0.0
    extra = f", {len(structure_events)} structure events" if structure_events else ""
    print(f"Wrote {path} ({len(result.swings)} swings{extra}, {ms:.1f}ms)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

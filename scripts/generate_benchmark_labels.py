#!/usr/bin/env python3
"""Generate benchmark label files from engine output (bootstrap ground truth)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared.types.models import Timeframe

from swing_engine import SwingEngine, load_manifest, write_labels
from swing_engine.datasets import LABELS_DIR
from tests.swing_detection.fixtures import (
    gold_candles,
    gold_range_candles,
    news_spike_candles,
    range_candles,
    swing_candles,
    trend_candles,
    volatile_candles,
)


def load_bars(spec) -> list:
    tf = Timeframe(spec.timeframe)
    sym = spec.symbol
    n = spec.bars
    regime = spec.regime
    if sym == "XAUUSD":
        if regime == "range":
            return gold_range_candles(n)
        return gold_candles(n)
    if regime == "range":
        return range_candles(n, timeframe=tf) if sym == "EURUSD" else swing_candles(
            n, base=1.27, wave=0.004, trend=0, period=10, symbol=sym, timeframe=tf
        )
    if regime == "volatile":
        return volatile_candles(n, timeframe=tf)
    if regime == "news":
        return news_spike_candles(n)
    return trend_candles(n, timeframe=tf) if sym == "EURUSD" else swing_candles(
        n, base=1.27, wave=0.005, trend=0.0002, period=12, symbol=sym, timeframe=tf
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate benchmark label JSON files")
    parser.add_argument("--version", default="1.4.0")
    parser.add_argument("--dataset", help="Single dataset id (default: all in manifest)")
    parser.add_argument("--only-confirmed", action="store_true", default=True)
    args = parser.parse_args()

    specs = load_manifest()
    if args.dataset:
        specs = [s for s in specs if s.id == args.dataset]
    if not specs:
        print("No datasets found", file=sys.stderr)
        return 1

    for spec in specs:
        bars = load_bars(spec)
        tf = Timeframe(spec.timeframe)
        result = SwingEngine(version=args.version).detect(bars, symbol=spec.symbol, timeframe=tf)
        swings = result.confirmed_swings if args.only_confirmed else result.swings
        path = write_labels(
            LABELS_DIR / spec.labels_file,
            symbol=spec.symbol,
            timeframe=spec.timeframe,
            regime=spec.regime,
            swings=swings,
            source_version=args.version,
            description=spec.description,
        )
        print(f"{spec.id}: {len(swings)} labels → {path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

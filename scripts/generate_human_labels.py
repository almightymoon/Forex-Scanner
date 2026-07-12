#!/usr/bin/env python3
"""Generate human-review labels from independent synthetic ground truth."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared.types.models import Timeframe

from swing_engine.datasets import LABELS_DIR, load_manifest
from swing_engine.ground_truth import write_ground_truth_file
from tests.swing_detection.fixtures import gold_candles, swing_candles, trend_candles


def load_bars(spec) -> list:
    tf = Timeframe(spec.timeframe)
    n = spec.bars
    if spec.symbol == "XAUUSD":
        return gold_candles(n, trend=0.4, wave=15.0, period=12)
    if spec.symbol == "EURUSD":
        return trend_candles(n, timeframe=tf)
    return swing_candles(
        n, base=1.27, wave=0.005, trend=0.0002, period=12, symbol=spec.symbol, timeframe=tf
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate independent human-review label files")
    parser.add_argument("--dataset", help="Single dataset id (default: all human_review)")
    args = parser.parse_args()

    specs = [s for s in load_manifest() if s.human_review]
    if args.dataset:
        specs = [s for s in specs if s.id == args.dataset]
    if not specs:
        print("No human-review datasets found", file=sys.stderr)
        return 1

    for spec in specs:
        bars = load_bars(spec)
        count = write_ground_truth_file(
            LABELS_DIR / spec.labels_file,
            bars=bars,
            symbol=spec.symbol,
            timeframe=spec.timeframe,
            regime=spec.regime,
            period=12 if spec.symbol != "EURUSD" else 12,
            description=spec.description,
        )
        print(f"{spec.id}: {count} independent labels → {LABELS_DIR / spec.labels_file}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

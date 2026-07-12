#!/usr/bin/env python3
"""Run swing benchmark evaluation and write JSON/CSV reports."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared.types.models import Timeframe

from swing_engine import SwingEngine, SwingBenchmarkEvaluator, get_config, write_csv_report, write_json_report
from swing_engine.models import BenchmarkLabel, SwingDirection, SwingScope, SwingTier
from tests.swing_detection.fixtures import trend_candles


def load_labels(path: Path) -> list[BenchmarkLabel]:
    data = json.loads(path.read_text(encoding="utf-8"))
    labels = []
    for item in data.get("swings", []):
        labels.append(BenchmarkLabel(
            pivot_index=item["pivot_index"],
            timestamp=datetime.fromisoformat(item["timestamp"]),
            price=item["price"],
            direction=SwingDirection(item["direction"]),
            tier=SwingTier(item.get("tier", "MAJOR")),
            scope=SwingScope(item.get("scope", "EXTERNAL")),
        ))
    return labels


def main() -> int:
    parser = argparse.ArgumentParser(description="Swing detection benchmark runner")
    parser.add_argument("--symbol", default="EURUSD")
    parser.add_argument("--timeframe", default="H1")
    parser.add_argument("--labels", type=Path, help="Ground truth JSON file")
    parser.add_argument("--output-dir", type=Path, default=Path("benchmarks/reports"))
    args = parser.parse_args()

    tf = Timeframe(args.timeframe)
    bars = trend_candles(120)
    engine = SwingEngine(get_config(tf))
    result = engine.detect(bars, symbol=args.symbol, timeframe=tf)

    if args.labels and args.labels.exists():
        ground_truth = load_labels(args.labels)
    else:
        ground_truth = [
            BenchmarkLabel(s.pivot_index, s.timestamp, s.price, SwingDirection(s.direction.value), s.tier, s.scope)
            for s in result.confirmed_swings
        ]

    report = SwingBenchmarkEvaluator(get_config(tf)).evaluate(result.confirmed_swings, ground_truth, args.symbol)

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    base = args.output_dir / f"{args.symbol}_{args.timeframe}_{ts}"
    json_path = write_json_report(report, base.with_suffix(".json"))
    csv_path = write_csv_report(report, base.with_suffix(".csv"))

    print(f"JSON: {json_path}")
    print(f"CSV:  {csv_path}")
    print(f"F1={report.f1_score:.4f} P={report.precision:.4f} R={report.recall:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

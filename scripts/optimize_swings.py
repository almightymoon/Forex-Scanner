#!/usr/bin/env python3
"""Parameter optimization runner for swing detection."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared.types.models import Timeframe

from swing_engine import ParamGrid, get_config, run_optimization, save_optimization_report
from swing_engine.models import BenchmarkLabel, SwingDirection, SwingScope, SwingTier
from tests.swing_detection.fixtures import gold_candles, trend_candles


def load_labels(path: Path) -> list[BenchmarkLabel]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [
        BenchmarkLabel(
            pivot_index=item["pivot_index"],
            timestamp=datetime.fromisoformat(item["timestamp"]),
            price=item["price"],
            direction=SwingDirection(item["direction"]),
            tier=SwingTier(item.get("tier", "MAJOR")),
            scope=SwingScope(item.get("scope", "EXTERNAL")),
        )
        for item in data.get("swings", [])
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Optimize swing detection parameters")
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--timeframe", default="H1")
    parser.add_argument("--version", default="1.3.0")
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--bars", type=int, default=200)
    parser.add_argument("--max", type=int, default=243, dest="max_combinations")
    parser.add_argument("--output", type=Path, default=Path("benchmarks/reports/optimization_results.json"))
    args = parser.parse_args()

    tf = Timeframe(args.timeframe)
    bars = gold_candles(args.bars) if args.symbol.upper() == "XAUUSD" else trend_candles(args.bars, timeframe=tf)
    labels = load_labels(args.labels)
    grid = ParamGrid()
    results = run_optimization(
        bars, labels, symbol=args.symbol, timeframe=tf,
        version=args.version, grid=grid, max_combinations=args.max_combinations,
    )
    save_optimization_report(results, args.output)
    if results:
        best = results[0]
        print(f"Best F1={best.report.f1_score:.4f} rank={best.rank_score:.2f}")
        print(f"Params: {best.params}")
    print(f"Report: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

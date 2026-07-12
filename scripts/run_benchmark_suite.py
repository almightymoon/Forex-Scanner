#!/usr/bin/env python3
"""Run full swing detection benchmark suite across all datasets."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared.types.models import Timeframe

from swing_engine.datasets import load_manifest, run_suite
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
    parser = argparse.ArgumentParser(description="Run swing benchmark dataset suite")
    parser.add_argument("--version", default="1.4.0")
    parser.add_argument("--dataset", help="Run single dataset id only")
    parser.add_argument("--output", type=Path, default=Path("benchmarks/reports/suite_report.json"))
    parser.add_argument("--fail-fast", action="store_true")
    args = parser.parse_args()

    specs = load_manifest()
    if args.dataset:
        specs = [s for s in specs if s.id == args.dataset]
    if not specs:
        print("No datasets in manifest", file=sys.stderr)
        return 1

    suite = run_suite(specs, load_bars, version=args.version)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(suite.to_dict(), indent=2), encoding="utf-8")

    print(f"Engine v{args.version} — {len(suite.results)} datasets")
    print("-" * 72)
    failed = 0
    for r in suite.results:
        status = "PASS" if r.passed else "FAIL"
        if not r.passed:
            failed += 1
        print(
            f"[{status}] {r.spec.id:22} F1={r.report.f1_score:.3f} "
            f"P={r.report.precision:.3f} R={r.report.recall:.3f} "
            f"delay={r.report.average_detection_delay_bars:.1f} "
            f"(min={r.spec.min_f1})"
        )
        if args.fail_fast and not r.passed:
            return 1

    print("-" * 72)
    print(f"By regime: {json.dumps(suite.to_dict()['by_regime'], indent=2)}")
    print(f"Report: {args.output}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

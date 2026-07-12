#!/usr/bin/env python3
"""Run full swing detection benchmark suite across all datasets."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared.types.models import Timeframe

from swing_engine.datasets import DASHBOARD_PATH, HISTORY_PATH, load_manifest, run_suite
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
    if spec.human_review or regime == "human":
        if sym == "XAUUSD":
            return gold_candles(n, trend=0.4, wave=15.0, period=12)
        if sym == "EURUSD":
            return trend_candles(n, timeframe=tf)
        return swing_candles(
            n, base=1.27, wave=0.005, trend=0.0002, period=12, symbol=sym, timeframe=tf
        )
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
    parser.add_argument("--version", default="2.0.0")
    parser.add_argument("--dataset", help="Run single dataset id only")
    parser.add_argument("--human-only", action="store_true", help="Run human-review datasets only")
    parser.add_argument("--output", type=Path, default=Path("benchmarks/reports/suite_report.json"))
    parser.add_argument("--no-history", action="store_true")
    parser.add_argument("--fail-fast", action="store_true")
    args = parser.parse_args()

    specs = load_manifest()
    if args.dataset:
        specs = [s for s in specs if s.id == args.dataset]
    elif args.human_only:
        specs = [s for s in specs if s.human_review]
    if not specs:
        print("No datasets in manifest", file=sys.stderr)
        return 1

    suite = run_suite(
        specs, load_bars, version=args.version,
        append_to_history=not args.no_history,
        write_dashboard=not args.no_history,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(suite.to_dict(), indent=2), encoding="utf-8")

    print(f"Engine v{args.version} — {len(suite.results)} datasets")
    print("-" * 88)
    failed = 0
    for r in suite.results:
        status = "PASS" if r.passed else "FAIL"
        if not r.passed:
            failed += 1
        hr = " [HUMAN]" if r.spec.human_review else ""
        print(
            f"[{status}] {r.spec.id:22}{hr} "
            f"F1={r.report.f1_score:.3f} majF1={r.major_f1:.3f} "
            f"majP={r.report.major_precision:.3f} majR={r.report.major_recall:.3f} "
            f"FP={r.report.false_positives} FN={r.report.false_negatives} "
            f"delay={r.report.average_detection_delay_bars:.1f}"
        )
        if args.fail_fast and not r.passed:
            return 1

    print("-" * 88)
    d = suite.to_dict()
    if d.get("human_review", {}).get("count"):
        print(f"Human review avg: {json.dumps(d['human_review'], indent=2)}")
    if not args.no_history:
        print(f"History: {HISTORY_PATH}")
        print(f"Dashboard: {DASHBOARD_PATH}")
    print(f"Report: {args.output}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

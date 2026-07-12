#!/usr/bin/env python3
"""Run swing benchmark evaluation with version comparison and reports."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared.types.models import Timeframe

from swing_engine import (
    SwingEngine,
    SwingBenchmarkEvaluator,
    get_config,
    write_comparison_charts,
    write_csv_report,
    write_json_report,
    write_markdown_report,
)
from swing_engine.models import BenchmarkLabel, SwingDirection, SwingScope, SwingTier
from swing_engine.regression import append_history, load_history, write_regression_dashboard
from swing_engine.versions import SUPPORTED_VERSIONS
from tests.swing_detection.fixtures import gold_candles, range_candles, trend_candles, volatile_candles


def load_labels(path: Path) -> tuple[list[BenchmarkLabel], str, str]:
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
    return labels, data.get("symbol", "EURUSD"), data.get("benchmark_version", "1.0")


def load_bars(regime: str, n: int, timeframe: Timeframe, symbol: str = "EURUSD"):
    if symbol.upper().replace("/", "") == "XAUUSD":
        return gold_candles(n)
    if regime == "range":
        return range_candles(n, timeframe=timeframe)
    if regime == "volatile":
        return volatile_candles(n, timeframe=timeframe)
    return trend_candles(n, timeframe=timeframe)


def main() -> int:
    parser = argparse.ArgumentParser(description="Swing detection benchmark runner")
    parser.add_argument("--symbol", default="EURUSD")
    parser.add_argument("--timeframe", default="H1")
    parser.add_argument("--labels", type=Path, help="Ground truth JSON file")
    parser.add_argument("--output-dir", type=Path, default=Path("benchmarks/reports"))
    parser.add_argument("--version", default="1.3.0")
    parser.add_argument("--compare-versions", nargs="*", help="Compare multiple versions")
    parser.add_argument("--bars", type=int, default=120)
    parser.add_argument("--regime", choices=["trend", "range", "volatile"], default="trend")
    parser.add_argument("--min-f1", type=float, default=None)
    parser.add_argument("--history", type=Path, default=Path("benchmarks/history/regression_history.jsonl"))
    parser.add_argument("--dashboard", type=Path, default=Path("benchmarks/reports/regression_dashboard.html"))
    parser.add_argument("--no-history", action="store_true", help="Skip appending to regression history")
    args = parser.parse_args()

    tf = Timeframe(args.timeframe)
    bars = load_bars(args.regime, args.bars, tf, args.symbol)
    versions = args.compare_versions or [args.version]

    reports = {}
    for ver in versions:
        if ver not in SUPPORTED_VERSIONS:
            print(f"Unknown version: {ver}", file=sys.stderr)
            return 1
        engine = SwingEngine(get_config(tf, version=ver, symbol=args.symbol), version=ver)
        result = engine.detect(bars, symbol=args.symbol, timeframe=tf)
        runtime = result.performance.runtime_ms if result.performance else None

        if args.labels and args.labels.exists():
            ground_truth, sym, bench_ver = load_labels(args.labels)
        else:
            ground_truth = [
                BenchmarkLabel(s.pivot_index, s.timestamp, s.price, s.direction, s.tier, s.scope)
                for s in result.confirmed_swings
            ]
            sym, bench_ver = args.symbol, "self"

        report = SwingBenchmarkEvaluator(get_config(tf, version=ver, symbol=args.symbol)).evaluate(
            result.confirmed_swings, ground_truth, sym,
            engine_version=ver, benchmark_version=bench_ver, regime=args.regime, runtime_ms=runtime,
        )
        if result.artifacts.repainting_stats:
            report.repainting_rate = result.artifacts.repainting_stats.get(
                "repainting_rate", report.repainting_rate
            )
        reports[ver] = report

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    base = args.output_dir / f"{args.symbol}_{args.timeframe}_{args.regime}_{ts}"
    primary = reports[versions[-1]]

    write_json_report(primary, base.with_suffix(".json"))
    write_csv_report(primary, base.with_suffix(".csv"))
    write_markdown_report(primary, base.with_suffix(".md"))
    if len(reports) > 1:
        write_comparison_charts(reports, base.with_name(base.name + "_comparison").with_suffix(".html"))

    print(f"JSON: {base.with_suffix('.json')}")
    print(f"MD:   {base.with_suffix('.md')}")
    for ver, r in reports.items():
        print(f"[{ver}] F1={r.f1_score:.4f} P={r.precision:.4f} R={r.recall:.4f} FP={r.false_positives} FN={r.false_negatives}")

    if not args.no_history:
        for ver in versions:
            append_history(reports[ver], args.history)
        write_regression_dashboard(load_history(args.history), args.dashboard)
        print(f"History:   {args.history}")
        print(f"Dashboard: {args.dashboard}")

    min_f1 = args.min_f1 or get_config(tf).evaluation.min_f1_regression
    if primary.f1_score < min_f1:
        print(f"FAIL: F1 {primary.f1_score:.4f} < {min_f1}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

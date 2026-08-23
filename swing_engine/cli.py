"""CLI for swing detection benchmarks — `python -m swing_engine`.

Examples:
  python -m swing_engine --symbol EURUSD --timeframe H1
  python -m swing_engine --benchmark swing --dataset validation
  python -m swing_engine --csv path.csv --labels path.json --version 2.3.0
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from shared.types.models import Timeframe
from swing_engine import SwingEngine, SwingBenchmarkEvaluator, get_config
from swing_engine.benchmark_data import load_candles_csv
from swing_engine.dataset_splits import (
    assert_not_tuning_locked_test,
    filter_candles_by_split,
    resolve_split,
    split_spec,
)
from swing_engine.models import BenchmarkLabel, SwingDirection, SwingScope, SwingTier
from swing_engine.versions import DEFAULT_VERSION, SUPPORTED_VERSIONS
from tests.swing_detection.fixtures import gold_candles, range_candles, trend_candles, volatile_candles


def _load_labels(path: Path) -> tuple[list[BenchmarkLabel], str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    labels: list[BenchmarkLabel] = []
    for item in data.get("swings", []):
        labels.append(
            BenchmarkLabel(
                pivot_index=item["pivot_index"],
                timestamp=datetime.fromisoformat(item["timestamp"]),
                price=item["price"],
                direction=SwingDirection(item["direction"]),
                tier=SwingTier(item.get("tier", "MAJOR")),
                scope=SwingScope(item.get("scope", "EXTERNAL")),
                confirmed_at_index=item.get("confirmed_at_index"),
            )
        )
    return labels, data.get("symbol", "EURUSD"), data.get("benchmark_version", "1.0")


def _synthetic_bars(symbol: str, regime: str, n: int, timeframe: Timeframe):
    if symbol.upper().replace("/", "") == "XAUUSD":
        return gold_candles(n)
    if regime == "range":
        return range_candles(n, timeframe=timeframe)
    if regime == "volatile":
        return volatile_candles(n, timeframe=timeframe)
    return trend_candles(n, timeframe=timeframe)


def _print_report(
    *,
    symbol: str,
    timeframe: str,
    version: str,
    detected: int,
    truth: int,
    report,
    split_label: str | None,
    candles: int,
    elapsed_s: float,
) -> None:
    print(f"Symbol: {symbol}")
    print(f"Timeframe: {timeframe}")
    print(f"Engine version: {version}")
    if split_label:
        print(f"Dataset split: {split_label}")
    print()
    print(f"Detected swings: {detected:,}")
    print(f"Ground truth:    {truth:,}")
    print()
    print(f"Precision:  {report.precision * 100:6.2f}%")
    print(f"Recall:     {report.recall * 100:6.2f}%")
    print(f"F1:         {report.f1_score * 100:6.2f}%")
    print()
    print(f"False positives: {report.false_positives}")
    print(f"False negatives: {report.false_negatives}")
    print(f"Avg confirmation delay: {report.average_detection_delay_bars:.2f} candles")
    print(f"Avg price deviation:    {report.average_price_error_pips:.2f} pips")
    print()
    print(f"Candles processed: {candles:,}")
    print(f"Processing time:   {elapsed_s:.3f}s")
    if elapsed_s > 0:
        print(f"Throughput:        {candles / elapsed_s:,.0f} candles/sec")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m swing_engine",
        description="Swing detection benchmark / evaluation CLI",
    )
    parser.add_argument("--benchmark", choices=["swing"], default="swing")
    parser.add_argument(
        "--dataset",
        default=None,
        help="Year split: development|validation|locked_test (filters CSV bars by year)",
    )
    parser.add_argument("--symbol", default="EURUSD")
    parser.add_argument("--timeframe", default="H1")
    parser.add_argument("--version", default=DEFAULT_VERSION)
    parser.add_argument("--csv", type=Path, default=None, help="Historical OHLC CSV")
    parser.add_argument("--labels", type=Path, default=None, help="Ground-truth JSON")
    parser.add_argument("--bars", type=int, default=240, help="Synthetic bar count when no CSV")
    parser.add_argument("--regime", choices=["trend", "range", "volatile"], default="trend")
    parser.add_argument(
        "--purpose",
        default="evaluate",
        help="Caller purpose (tune/optimize rejected on locked_test)",
    )
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args(argv)

    if args.version not in SUPPORTED_VERSIONS:
        print(f"Unknown version: {args.version}", file=sys.stderr)
        return 1

    tf = Timeframe(args.timeframe)
    split_label = None
    if args.dataset:
        split = resolve_split(args.dataset)
        spec = split_spec(split)
        assert_not_tuning_locked_test(split, purpose=args.purpose)
        split_label = spec.label
        if spec.locked:
            print(f"*** {spec.label} — evaluation only; do not tune against this split ***")
            print()

    if args.csv:
        candles = load_candles_csv(args.csv, symbol=args.symbol, timeframe=tf)
        if args.dataset:
            candles = filter_candles_by_split(candles, args.dataset)
        if not candles:
            print("No candles after dataset filter.", file=sys.stderr)
            return 1
    else:
        candles = _synthetic_bars(args.symbol, args.regime, args.bars, tf)

    ground_truth: list[BenchmarkLabel] | None = None
    bench_ver = "self"
    if args.labels and args.labels.exists():
        from swing_engine.dataset_splits import filter_by_split_years

        ground_truth, sym_from_labels, bench_ver = _load_labels(args.labels)
        args.symbol = args.symbol or sym_from_labels
        if args.dataset:
            ground_truth = filter_by_split_years(ground_truth, args.dataset)

    engine = SwingEngine(get_config(tf, version=args.version, symbol=args.symbol), version=args.version)
    t0 = time.perf_counter()
    result = engine.detect(candles, symbol=args.symbol, timeframe=tf)
    elapsed = time.perf_counter() - t0

    confirmed = result.confirmed_swings
    if ground_truth is None:
        print(
            "Benchmark blocked: ground-truth annotations are not available.\n"
            "Pass --labels PATH to evaluate precision/recall/F1.\n"
            f"Detected {len(confirmed)} confirmed swings on {len(candles)} candles "
            f"(engine {args.version}).",
            file=sys.stderr,
        )
        if args.json_out:
            args.json_out.write_text(
                json.dumps(
                    {
                        "blocked": True,
                        "reason": "ground_truth_missing",
                        "symbol": args.symbol,
                        "timeframe": tf.value,
                        "engine_version": args.version,
                        "detected_swings": len(confirmed),
                        "candles": len(candles),
                        "dataset_split": split_label,
                        "elapsed_seconds": elapsed,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
        return 2

    report = SwingBenchmarkEvaluator(get_config(tf, version=args.version, symbol=args.symbol)).evaluate(
        confirmed,
        ground_truth,
        args.symbol,
        engine_version=args.version,
        benchmark_version=bench_ver,
        regime=args.regime,
        runtime_ms=elapsed * 1000,
        candles=candles,
    )

    _print_report(
        symbol=args.symbol,
        timeframe=tf.value,
        version=args.version,
        detected=len(confirmed),
        truth=len(ground_truth),
        report=report,
        split_label=split_label,
        candles=len(candles),
        elapsed_s=elapsed,
    )

    if args.json_out:
        payload = report.to_dict() if hasattr(report, "to_dict") else {
            "precision": report.precision,
            "recall": report.recall,
            "f1_score": report.f1_score,
            "false_positives": report.false_positives,
            "false_negatives": report.false_negatives,
            "engine_version": args.version,
            "dataset_split": split_label,
        }
        args.json_out.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

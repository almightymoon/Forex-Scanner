#!/usr/bin/env python3
"""Confidence calibration report — predicted vs actual match rate by decile."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared.types.models import Timeframe

from swing_engine import SwingEngine, calibrate_confidence, get_config, load_labels, load_manifest
from swing_engine.datasets import LABELS_DIR
from scripts.run_benchmark_suite import load_bars


def main() -> int:
    parser = argparse.ArgumentParser(description="Run confidence calibration analysis")
    parser.add_argument("--version", default="2.0.0")
    parser.add_argument("--dataset", default="XAUUSD_H1_human")
    parser.add_argument("--output", type=Path, default=Path("benchmarks/reports/calibration_report.json"))
    args = parser.parse_args()

    specs = load_manifest()
    spec = next((s for s in specs if s.id == args.dataset), None)
    if not spec:
        print(f"Unknown dataset: {args.dataset}", file=sys.stderr)
        return 1

    bars = load_bars(spec)
    tf = Timeframe(spec.timeframe)
    cfg = get_config(tf, version=args.version, symbol=spec.symbol)
    result = SwingEngine(cfg, version=args.version).detect(bars, symbol=spec.symbol, timeframe=tf)
    labels, _ = load_labels(LABELS_DIR / spec.labels_file)

    report = calibrate_confidence(result.confirmed_swings, labels, cfg, symbol=spec.symbol)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")

    print(f"Calibration — {spec.id} v{args.version}")
    print(f"Mean error: {report.mean_calibration_error:.3f} · matched {report.matched_swings}/{report.total_swings}")
    print("-" * 56)
    for b in report.buckets:
        print(f"  {b.label:12} pred={b.predicted_confidence:.2f} actual={b.actual_accuracy:.2f} "
              f"n={b.count} err={b.calibration_error:.3f}")
    print(f"Report: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

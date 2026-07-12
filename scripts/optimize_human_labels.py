#!/usr/bin/env python3
"""Optimize swing parameters against human-review benchmark datasets."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared.types.models import Timeframe

from swing_engine import ParamGrid, load_labels, load_manifest, run_optimization, save_optimization_report
from swing_engine.datasets import LABELS_DIR
from scripts.generate_human_labels import load_bars


def main() -> int:
    parser = argparse.ArgumentParser(description="Optimize against human-review labels")
    parser.add_argument("--version", default="2.0.0")
    parser.add_argument("--dataset", default="XAUUSD_H1_human")
    parser.add_argument("--max-combinations", type=int, default=200)
    parser.add_argument("--output", type=Path, default=Path("benchmarks/reports/optimize_human.json"))
    args = parser.parse_args()

    specs = [s for s in load_manifest() if s.human_review]
    spec = next((s for s in specs if s.id == args.dataset), None)
    if not spec:
        print(f"Unknown human dataset: {args.dataset}", file=sys.stderr)
        return 1

    bars = load_bars(spec)
    labels, _ = load_labels(LABELS_DIR / spec.labels_file)
    tf = Timeframe(spec.timeframe)

    grid = ParamGrid(
        pivot_left_lookback=(2, 3),
        confirmation_delay_bars=(2, 3),
        leg_min_atr_multiple=(0.25, 0.35),
        quality_min_acceptable=(40.0, 50.0),
        major_min_atr_multiple=(1.0, 1.2),
        confirmation_score_threshold=(65.0, 70.0, 75.0),
        min_pivot_strength=(6.0, 8.0),
    )

    results = run_optimization(
        bars, labels,
        symbol=spec.symbol,
        timeframe=tf,
        version=args.version,
        grid=grid,
        max_combinations=args.max_combinations,
        major_focus=True,
    )
    save_optimization_report(results, args.output)

    best = results[0] if results else None
    print(f"Optimized {spec.id} — {len(results)} combinations")
    if best:
        print(f"Best rank={best.rank_score:.2f} major_P={best.report.major_precision:.3f} "
              f"major_R={best.report.major_recall:.3f} delay={best.report.average_detection_delay_bars:.1f}")
        print(f"Params: {json.dumps(best.params)}")
    print(f"Report: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

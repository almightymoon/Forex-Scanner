#!/usr/bin/env python3
"""Tune the v2.2 recursive XAUUSD H1 hierarchy without test leakage.

The v2.1 first-level pivot detector is frozen.  This command searches only the
second-level hierarchy thresholds on TRAIN samples, freezes the selected pair,
and evaluates chronological VALIDATION exactly once.

The current benchmark contains AI-assisted expert draft labels and no locked
TEST split.  Results are development evidence, not production certification.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared.types.models import Timeframe
from swing_engine.config import SwingEngineConfig, get_config
from swing_engine.datasets import (
    LABELS_DIR,
    DatasetSpec,
    load_labels,
    load_manifest,
    load_real_bars,
)
from swing_engine.detector import SwingEngine
from swing_engine.evaluation import SwingBenchmarkEvaluator
from swing_engine.models import BenchmarkLabel, DetectedSwing, SwingScope, SwingTier

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = (
    REPO_ROOT
    / "benchmarks"
    / "datasets"
    / "XAUUSD_H1.human.manifest.json"
)
DEFAULT_OUTPUT = (
    REPO_ROOT
    / "benchmarks"
    / "reports"
    / "XAUUSD_H1_v2_2_hierarchy_search.json"
)


def _csv_floats(value: str) -> list[float]:
    values = [float(item.strip()) for item in value.split(",") if item.strip()]
    if not values:
        raise argparse.ArgumentTypeError("at least one numeric value is required")
    return values


def _load_sample(
    spec: DatasetSpec,
    manifest: Path,
) -> tuple[list, list[BenchmarkLabel]]:
    bars = load_real_bars(spec, manifest_path=manifest)
    labels, _ = load_labels(
        LABELS_DIR / spec.labels_file,
        sample_id=spec.sample_id,
    )

    if spec.labelable_start_index is not None:
        labels = [
            label
            for label in labels
            if label.pivot_index >= spec.labelable_start_index
        ]
    if spec.labelable_end_index is not None:
        labels = [
            label
            for label in labels
            if label.pivot_index <= spec.labelable_end_index
        ]

    return bars, labels


def _configured_engine(
    spec: DatasetSpec,
    *,
    version: str,
    hierarchy_reversal_atr: float | None = None,
    provisional_prominence_atr: float | None = None,
) -> tuple[SwingEngine, SwingEngineConfig]:
    timeframe = Timeframe(spec.timeframe)
    config = get_config(
        timeframe,
        version=version,
        symbol=spec.symbol,
    )

    if hierarchy_reversal_atr is not None:
        classification = dataclasses.replace(
            config.classification,
            hierarchy_reversal_atr=hierarchy_reversal_atr,
            hierarchy_include_provisional=True,
            hierarchy_provisional_prominence_atr=(
                provisional_prominence_atr
                if provisional_prominence_atr is not None
                else config.classification.hierarchy_provisional_prominence_atr
            ),
        )
        config = dataclasses.replace(
            config,
            classification=classification,
        )

    return SwingEngine(config, version=version), config


def _detect(
    spec: DatasetSpec,
    bars: list,
    *,
    version: str,
    hierarchy_reversal_atr: float | None = None,
    provisional_prominence_atr: float | None = None,
) -> tuple[list[DetectedSwing], SwingEngineConfig]:
    engine, config = _configured_engine(
        spec,
        version=version,
        hierarchy_reversal_atr=hierarchy_reversal_atr,
        provisional_prominence_atr=provisional_prominence_atr,
    )
    timeframe = Timeframe(spec.timeframe)
    result = engine.detect(
        bars,
        symbol=spec.symbol,
        timeframe=timeframe,
    )
    predictions = result.confirmed_swings

    if spec.labelable_start_index is not None:
        predictions = [
            swing
            for swing in predictions
            if swing.pivot_index >= spec.labelable_start_index
        ]
    if spec.labelable_end_index is not None:
        predictions = [
            swing
            for swing in predictions
            if swing.pivot_index <= spec.labelable_end_index
        ]

    return predictions, config


def _evaluate_sample(
    spec: DatasetSpec,
    bars: list,
    labels: list[BenchmarkLabel],
    predictions: list[DetectedSwing],
    config: SwingEngineConfig,
    *,
    version: str,
) -> dict[str, Any]:
    evaluation = config.evaluation
    if spec.evaluation_tolerance_bars:
        evaluation = dataclasses.replace(
            evaluation,
            index_match_tolerance_bars=spec.evaluation_tolerance_bars,
        )

    report = SwingBenchmarkEvaluator(
        dataclasses.replace(config, evaluation=evaluation)
    ).evaluate(
        predictions,
        labels,
        spec.symbol,
        engine_version=version,
        benchmark_version="XAUUSD_H1_AI_DRAFT_V1",
        regime=spec.regime,
        candles=bars,
        bar_count=len(bars),
    )
    report_dict = report.to_dict()

    major_external_predicted = sum(
        1
        for swing in predictions
        if swing.tier is SwingTier.MAJOR
        and swing.scope is SwingScope.EXTERNAL
    )
    major_external_truth = sum(
        1
        for label in labels
        if label.tier is SwingTier.MAJOR
        and label.scope is SwingScope.EXTERNAL
    )
    major_external_true_positives = sum(
        1
        for pair in report_dict["matched_pairs"]
        if pair["predicted_tier"] == SwingTier.MAJOR.value
        and pair["predicted_scope"] == SwingScope.EXTERNAL.value
        and pair["ground_truth_tier"] == SwingTier.MAJOR.value
        and pair["ground_truth_scope"] == SwingScope.EXTERNAL.value
    )

    hierarchy_states = Counter(
        swing.hierarchy_state.value
        if swing.hierarchy_state is not None
        else "NONE"
        for swing in predictions
    )

    return {
        "dataset_id": spec.id,
        "sample_id": spec.sample_id,
        "split": spec.split,
        "regime": spec.regime,
        "predicted": len(predictions),
        "ground_truth": len(labels),
        "hierarchy_states": dict(sorted(hierarchy_states.items())),
        "major_external_predicted": major_external_predicted,
        "major_external_truth": major_external_truth,
        "major_external_true_positives": major_external_true_positives,
        **report_dict,
    }


def _f1(precision: float, recall: float) -> float:
    return (
        2.0 * precision * recall / (precision + recall)
        if precision + recall
        else 0.0
    )


def _aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    predicted = sum(int(row["predicted"]) for row in rows)
    ground_truth = sum(int(row["ground_truth"]) for row in rows)

    location_tp = sum(int(row["true_positives"]) for row in rows)
    location_fp = sum(int(row["false_positives"]) for row in rows)
    location_fn = sum(int(row["false_negatives"]) for row in rows)

    location_precision = (
        location_tp / (location_tp + location_fp)
        if location_tp + location_fp
        else 0.0
    )
    location_recall = (
        location_tp / (location_tp + location_fn)
        if location_tp + location_fn
        else 0.0
    )

    semantic_tp = sum(
        int(row["semantic_true_positives"]) for row in rows
    )
    semantic_precision = semantic_tp / predicted if predicted else 0.0
    semantic_recall = semantic_tp / ground_truth if ground_truth else 0.0

    major_external_predicted = sum(
        int(row["major_external_predicted"]) for row in rows
    )
    major_external_truth = sum(
        int(row["major_external_truth"]) for row in rows
    )
    major_external_tp = sum(
        int(row["major_external_true_positives"]) for row in rows
    )
    major_external_precision = (
        major_external_tp / major_external_predicted
        if major_external_predicted
        else 0.0
    )
    major_external_recall = (
        major_external_tp / major_external_truth
        if major_external_truth
        else 0.0
    )

    weighted_tier_correct = sum(
        float(row["tier_accuracy"]) * int(row["true_positives"])
        for row in rows
    )
    weighted_scope_correct = sum(
        float(row["scope_accuracy"]) * int(row["true_positives"])
        for row in rows
    )
    sample_semantic_f1 = [
        float(row["semantic_f1"]) for row in rows
    ]
    hierarchy_states: Counter[str] = Counter()
    for row in rows:
        hierarchy_states.update(row.get("hierarchy_states", {}))

    return {
        "datasets": len(rows),
        "predicted": predicted,
        "ground_truth": ground_truth,
        "hierarchy_states": dict(sorted(hierarchy_states.items())),
        "location": {
            "true_positives": location_tp,
            "false_positives": location_fp,
            "false_negatives": location_fn,
            "precision": round(location_precision, 6),
            "recall": round(location_recall, 6),
            "f1": round(_f1(location_precision, location_recall), 6),
        },
        "semantic": {
            "true_positives": semantic_tp,
            "false_positives": predicted - semantic_tp,
            "false_negatives": ground_truth - semantic_tp,
            "precision": round(semantic_precision, 6),
            "recall": round(semantic_recall, 6),
            "f1": round(_f1(semantic_precision, semantic_recall), 6),
            "macro_sample_f1": round(
                sum(sample_semantic_f1) / len(sample_semantic_f1),
                6,
            )
            if sample_semantic_f1
            else 0.0,
            "worst_sample_f1": round(min(sample_semantic_f1), 6)
            if sample_semantic_f1
            else 0.0,
            "tier_accuracy_on_location_matches": round(
                weighted_tier_correct / location_tp,
                6,
            )
            if location_tp
            else 0.0,
            "scope_accuracy_on_location_matches": round(
                weighted_scope_correct / location_tp,
                6,
            )
            if location_tp
            else 0.0,
        },
        "major_external": {
            "true_positives": major_external_tp,
            "predicted": major_external_predicted,
            "ground_truth": major_external_truth,
            "precision": round(major_external_precision, 6),
            "recall": round(major_external_recall, 6),
            "f1": round(
                _f1(
                    major_external_precision,
                    major_external_recall,
                ),
                6,
            ),
        },
    }


def _aggregate_by_regime(
    rows: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["regime"])].append(row)

    return {
        regime: _aggregate(items)
        for regime, items in sorted(grouped.items())
    }


def _run_profile(
    specs: list[DatasetSpec],
    samples: dict[str, tuple[list, list[BenchmarkLabel]]],
    *,
    version: str,
    hierarchy_reversal_atr: float | None = None,
    provisional_prominence_atr: float | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for spec in specs:
        bars, labels = samples[spec.id]
        predictions, config = _detect(
            spec,
            bars,
            version=version,
            hierarchy_reversal_atr=hierarchy_reversal_atr,
            provisional_prominence_atr=provisional_prominence_atr,
        )
        rows.append(
            _evaluate_sample(
                spec,
                bars,
                labels,
                predictions,
                config,
                version=version,
            )
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
    )
    parser.add_argument("--version", default="2.2.0")
    parser.add_argument("--baseline-version", default="2.1.0")
    parser.add_argument(
        "--hierarchy-thresholds",
        type=_csv_floats,
        default=[4.0, 4.25, 4.5, 4.75, 5.0, 5.25],
    )
    parser.add_argument(
        "--provisional-thresholds",
        type=_csv_floats,
        default=[4.0, 4.5, 5.0, 5.5, 6.0],
    )
    parser.add_argument(
        "--train-major-external-precision-floor",
        type=float,
        default=0.90,
    )
    parser.add_argument(
        "--train-worst-sample-semantic-f1-floor",
        type=float,
        default=0.50,
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
    )
    args = parser.parse_args()

    specs = load_manifest(args.manifest)
    train = [
        spec for spec in specs if spec.split.upper() == "TRAIN"
    ]
    validation = [
        spec
        for spec in specs
        if spec.split.upper() == "VALIDATION"
    ]
    test = [
        spec for spec in specs if spec.split.upper() == "TEST"
    ]

    if not train or not validation:
        raise SystemExit(
            "manifest must contain both TRAIN and VALIDATION samples"
        )
    if test:
        raise SystemExit(
            "this tuning command refuses to inspect locked TEST samples"
        )

    # Load only TRAIN material during selection. Validation candles and labels
    # are not read until both hierarchy thresholds are frozen.
    train_samples = {
        spec.id: _load_sample(spec, args.manifest)
        for spec in train
    }

    grid: list[dict[str, Any]] = []
    for hierarchy_threshold in args.hierarchy_thresholds:
        for provisional_threshold in args.provisional_thresholds:
            train_rows = _run_profile(
                train,
                train_samples,
                version=args.version,
                hierarchy_reversal_atr=hierarchy_threshold,
                provisional_prominence_atr=provisional_threshold,
            )
            grid.append(
                {
                    "hierarchy_reversal_atr": hierarchy_threshold,
                    "provisional_prominence_atr": provisional_threshold,
                    "train": _aggregate(train_rows),
                }
            )

    for row in grid:
        row["eligible"] = (
            row["train"]["major_external"]["precision"]
            >= args.train_major_external_precision_floor
            and row["train"]["semantic"]["worst_sample_f1"]
            >= args.train_worst_sample_semantic_f1_floor
        )

    eligible = [row for row in grid if row["eligible"]]
    if not eligible:
        raise SystemExit(
            "no hierarchy profile satisfies both TRAIN robustness floors"
        )

    selected = max(
        eligible,
        key=lambda row: (
            row["train"]["semantic"]["f1"],
            row["train"]["semantic"]["macro_sample_f1"],
            row["train"]["major_external"]["f1"],
            row["train"]["major_external"]["precision"],
        ),
    )
    hierarchy_threshold = float(
        selected["hierarchy_reversal_atr"]
    )
    provisional_threshold = float(
        selected["provisional_prominence_atr"]
    )

    selected_train_rows = _run_profile(
        train,
        train_samples,
        version=args.version,
        hierarchy_reversal_atr=hierarchy_threshold,
        provisional_prominence_atr=provisional_threshold,
    )

    # VALIDATION is first loaded and evaluated here, after both thresholds are
    # frozen. No validation candle, label, prediction, or metric participates
    # in selection.
    validation_samples = {
        spec.id: _load_sample(spec, args.manifest)
        for spec in validation
    }
    selected_validation_rows = _run_profile(
        validation,
        validation_samples,
        version=args.version,
        hierarchy_reversal_atr=hierarchy_threshold,
        provisional_prominence_atr=provisional_threshold,
    )
    selected_rows = selected_train_rows + selected_validation_rows

    baseline_train_rows = _run_profile(
        train,
        train_samples,
        version=args.baseline_version,
    )
    baseline_validation_rows = _run_profile(
        validation,
        validation_samples,
        version=args.baseline_version,
    )
    baseline_rows = baseline_train_rows + baseline_validation_rows

    selected_train = _aggregate(selected_train_rows)
    selected_validation = _aggregate(selected_validation_rows)
    selected_all = _aggregate(selected_rows)

    baseline_train = _aggregate(baseline_train_rows)
    baseline_validation = _aggregate(baseline_validation_rows)
    baseline_all = _aggregate(baseline_rows)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(
            timespec="seconds"
        ),
        "engine_version": args.version,
        "baseline_version": args.baseline_version,
        "benchmark": "XAUUSD_H1_AI_ASSISTED_EXPERT_DRAFT",
        "warning": (
            "No locked TEST split exists; do not treat these metrics "
            "as production certification."
        ),
        "frozen_first_level_location_profile": {
            "leg_min_atr_multiple": 2.8,
            "note": (
                "v2.2 changes hierarchy only; v2.1 pivot locations "
                "and first-level confirmation remain frozen."
            ),
        },
        "selection_policy": {
            "data_used": "TRAIN only",
            "eligibility": {
                "major_external_precision_floor": (
                    args.train_major_external_precision_floor
                ),
                "worst_sample_semantic_f1_floor": (
                    args.train_worst_sample_semantic_f1_floor
                ),
            },
            "objective": (
                "max aggregate TRAIN semantic F1, then macro sample "
                "semantic F1, Major External F1, and precision"
            ),
            "validation_policy": (
                "chronological VALIDATION evaluated exactly once "
                "after both thresholds were frozen"
            ),
        },
        "selected": {
            "hierarchy_reversal_atr": hierarchy_threshold,
            "provisional_prominence_atr": provisional_threshold,
        },
        "grid": grid,
        "baseline": {
            "train": baseline_train,
            "validation": baseline_validation,
            "all_development": baseline_all,
            "by_regime": _aggregate_by_regime(baseline_rows),
        },
        "results": {
            "train": selected_train,
            "validation": selected_validation,
            "all_development": selected_all,
            "by_regime": _aggregate_by_regime(selected_rows),
        },
        "improvement": {
            "validation_semantic_f1_gain": round(
                selected_validation["semantic"]["f1"]
                - baseline_validation["semantic"]["f1"],
                6,
            ),
            "validation_tier_accuracy_gain": round(
                selected_validation["semantic"][
                    "tier_accuracy_on_location_matches"
                ]
                - baseline_validation["semantic"][
                    "tier_accuracy_on_location_matches"
                ],
                6,
            ),
            "validation_scope_accuracy_gain": round(
                selected_validation["semantic"][
                    "scope_accuracy_on_location_matches"
                ]
                - baseline_validation["semantic"][
                    "scope_accuracy_on_location_matches"
                ],
                6,
            ),
            "validation_major_external_f1_gain": round(
                selected_validation["major_external"]["f1"]
                - baseline_validation["major_external"]["f1"],
                6,
            ),
            "location_prediction_change": (
                selected_all["predicted"]
                - baseline_all["predicted"]
            ),
            "location_false_positive_change": (
                selected_all["location"]["false_positives"]
                - baseline_all["location"]["false_positives"]
            ),
            "location_false_negative_change": (
                selected_all["location"]["false_negatives"]
                - baseline_all["location"]["false_negatives"]
            ),
        },
        "baseline_per_sample": baseline_rows,
        "per_sample": selected_rows,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(payload["selected"], indent=2))
    print(
        json.dumps(
            {
                "train": payload["results"]["train"],
                "validation": payload["results"]["validation"],
                "all_development": payload["results"][
                    "all_development"
                ],
                "improvement": payload["improvement"],
            },
            indent=2,
        )
    )
    print(f"Report: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

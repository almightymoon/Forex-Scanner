#!/usr/bin/env python3
"""Tune the causal XAUUSD H1 structural swing profile without test leakage.

The script selects parameters on TRAIN samples only, then evaluates the chosen
configuration exactly once on the chronological VALIDATION samples.  The
current AI-assisted draft benchmark has no locked TEST split, so results are
development evidence rather than production certification.
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
from swing_engine.datasets import LABELS_DIR, DatasetSpec, load_labels, load_manifest, load_real_bars
from swing_engine.detector import SwingEngine
from swing_engine.evaluation import SwingBenchmarkEvaluator
from swing_engine.models import BenchmarkLabel, DetectedSwing, SwingScope, SwingTier

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = REPO_ROOT / "benchmarks" / "datasets" / "XAUUSD_H1.human.manifest.json"
DEFAULT_OUTPUT = REPO_ROOT / "benchmarks" / "reports" / "XAUUSD_H1_v2_1_tuning_search.json"


def _csv_floats(value: str) -> list[float]:
    values = [float(item.strip()) for item in value.split(",") if item.strip()]
    if not values:
        raise argparse.ArgumentTypeError("at least one numeric value is required")
    return values


def _load_sample(spec: DatasetSpec, manifest: Path) -> tuple[list, list[BenchmarkLabel]]:
    bars = load_real_bars(spec, manifest_path=manifest)
    labels, _ = load_labels(LABELS_DIR / spec.labels_file, sample_id=spec.sample_id)
    start = spec.labelable_start_index
    end = spec.labelable_end_index
    if start is not None:
        labels = [label for label in labels if label.pivot_index >= start]
    if end is not None:
        labels = [label for label in labels if label.pivot_index <= end]
    return bars, labels


def _detect(
    spec: DatasetSpec,
    bars: list,
    *,
    leg_atr: float,
    version: str,
) -> tuple[list[DetectedSwing], SwingEngineConfig]:
    timeframe = Timeframe(spec.timeframe)
    config = get_config(timeframe, version=version, symbol=spec.symbol)
    config = dataclasses.replace(
        config,
        leg=dataclasses.replace(config.leg, min_atr_multiple=leg_atr),
    )
    result = SwingEngine(config, version=version).detect(
        bars,
        symbol=spec.symbol,
        timeframe=timeframe,
    )
    predictions = result.confirmed_swings
    if spec.labelable_start_index is not None:
        predictions = [
            swing for swing in predictions if swing.pivot_index >= spec.labelable_start_index
        ]
    if spec.labelable_end_index is not None:
        predictions = [
            swing for swing in predictions if swing.pivot_index <= spec.labelable_end_index
        ]
    return predictions, config


def _detect_configured(
    spec: DatasetSpec,
    bars: list,
    *,
    version: str,
) -> tuple[list[DetectedSwing], SwingEngineConfig]:
    """Run a frozen profile without injecting tuning overrides."""
    timeframe = Timeframe(spec.timeframe)
    config = get_config(timeframe, version=version, symbol=spec.symbol)
    result = SwingEngine(config, version=version).detect(
        bars,
        symbol=spec.symbol,
        timeframe=timeframe,
    )
    predictions = result.confirmed_swings
    if spec.labelable_start_index is not None:
        predictions = [
            swing for swing in predictions if swing.pivot_index >= spec.labelable_start_index
        ]
    if spec.labelable_end_index is not None:
        predictions = [
            swing for swing in predictions if swing.pivot_index <= spec.labelable_end_index
        ]
    return predictions, config


def _reclassify(
    predictions: list[DetectedSwing],
    config: SwingEngineConfig,
    threshold: float,
) -> list[DetectedSwing]:
    classification = config.classification
    output: list[DetectedSwing] = []
    for original in predictions:
        swing = dataclasses.replace(original, metadata=dict(original.metadata))
        leg_atr = float(swing.metadata.get("leg_atr", 0.0))
        reversal_atr = float(swing.metadata.get("structural_reversal_atr", leg_atr))
        prominence = (
            classification.structural_leg_weight * leg_atr
            + classification.structural_reversal_weight * reversal_atr
        )
        swing.metadata["structural_prominence_atr"] = round(prominence, 3)
        swing.tier = SwingTier.MAJOR if prominence >= threshold else SwingTier.MINOR
        swing.scope = SwingScope.EXTERNAL if swing.tier is SwingTier.MAJOR else SwingScope.INTERNAL
        output.append(swing)
    return output


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
    report = SwingBenchmarkEvaluator(dataclasses.replace(config, evaluation=evaluation)).evaluate(
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
    predicted_types = Counter(
        f"{swing.tier.value}_{swing.scope.value}_{swing.direction.value}"
        for swing in predictions
    )
    semantic_true_positives = Counter(
        f"{pair['predicted_tier']}_{pair['predicted_scope']}_{pair['predicted_direction']}"
        for pair in report_dict["matched_pairs"]
        if pair["full_semantic_match"]
    )
    predicted_type_errors = {
        key: count - semantic_true_positives.get(key, 0)
        for key, count in sorted(predicted_types.items())
        if count - semantic_true_positives.get(key, 0) > 0
    }
    return {
        "dataset_id": spec.id,
        "split": spec.split,
        "regime": spec.regime,
        "predicted": len(predictions),
        "predicted_type_errors": predicted_type_errors,
        **report_dict,
    }


def _aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    predicted = sum(int(row["predicted"]) for row in rows)
    tp = sum(int(row["true_positives"]) for row in rows)
    fp = sum(int(row["false_positives"]) for row in rows)
    fn = sum(int(row["false_negatives"]) for row in rows)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "datasets": len(rows),
        "predicted": predicted,
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "f1": round(f1, 6),
        "macro_major_external_f1": round(
            sum(float(row["major_external_f1"]) for row in rows) / len(rows), 6
        ) if rows else 0.0,
    }


def _aggregate_by_regime(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["regime"])].append(row)
    return {regime: _aggregate(items) for regime, items in sorted(grouped.items())}


def _aggregate_predicted_type_errors(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for row in rows:
        counts.update(row.get("predicted_type_errors", {}))
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--version", default="2.1.0")
    parser.add_argument("--baseline-version", default="2.0.0")
    parser.add_argument("--leg-thresholds", type=_csv_floats, default=[2.4, 2.6, 2.8, 3.0])
    parser.add_argument(
        "--classification-thresholds",
        type=_csv_floats,
        default=[4.4, 4.6, 4.8, 5.0],
    )
    parser.add_argument("--train-recall-floor", type=float, default=0.84)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    specs = load_manifest(args.manifest)
    train = [spec for spec in specs if spec.split.upper() == "TRAIN"]
    validation = [spec for spec in specs if spec.split.upper() == "VALIDATION"]
    test = [spec for spec in specs if spec.split.upper() == "TEST"]
    if not train or not validation:
        raise SystemExit("manifest must contain both TRAIN and VALIDATION samples")
    if test:
        raise SystemExit("this tuning command refuses to touch locked TEST samples")

    samples = {spec.id: (*_load_sample(spec, args.manifest), spec) for spec in specs}

    location_grid: list[dict[str, Any]] = []
    prediction_cache: dict[float, dict[str, tuple[list[DetectedSwing], SwingEngineConfig]]] = {}

    for leg_atr in args.leg_thresholds:
        cached: dict[str, tuple[list[DetectedSwing], SwingEngineConfig]] = {}
        train_rows: list[dict[str, Any]] = []
        for spec in train:
            bars, labels, _ = samples[spec.id]
            predictions, config = _detect(
                spec,
                bars,
                leg_atr=leg_atr,
                version=args.version,
            )
            cached[spec.id] = (predictions, config)
            if spec.split.upper() == "TRAIN":
                train_rows.append(
                    _evaluate_sample(
                        spec,
                        bars,
                        labels,
                        predictions,
                        config,
                        version=args.version,
                    )
                )
        prediction_cache[leg_atr] = cached
        location_grid.append({"leg_atr": leg_atr, "train": _aggregate(train_rows)})

    eligible = [
        row for row in location_grid if row["train"]["recall"] >= args.train_recall_floor
    ]
    if not eligible:
        raise SystemExit("no leg threshold satisfies the TRAIN recall floor")
    selected_location = max(
        eligible,
        key=lambda row: (row["train"]["f1"], row["train"]["precision"]),
    )
    selected_leg = float(selected_location["leg_atr"])

    classification_grid: list[dict[str, Any]] = []
    for threshold in args.classification_thresholds:
        rows: list[dict[str, Any]] = []
        for spec in train:
            bars, labels, _ = samples[spec.id]
            predictions, config = prediction_cache[selected_leg][spec.id]
            classified = _reclassify(predictions, config, threshold)
            rows.append(
                _evaluate_sample(
                    spec,
                    bars,
                    labels,
                    classified,
                    config,
                    version=args.version,
                )
            )
        classification_grid.append(
            {"structural_prominence_atr": threshold, "train": _aggregate(rows)}
        )
    selected_classification = max(
        classification_grid,
        key=lambda row: (
            row["train"]["macro_major_external_f1"],
            row["train"]["f1"],
        ),
    )
    selected_prominence = float(selected_classification["structural_prominence_atr"])

    # Only now, after both parameters are frozen, run the selected profile on
    # chronological VALIDATION. No validation prediction or metric participates
    # in either search.
    final_rows: list[dict[str, Any]] = []
    for spec in specs:
        bars, labels, _ = samples[spec.id]
        if spec.id in prediction_cache[selected_leg]:
            predictions, config = prediction_cache[selected_leg][spec.id]
        else:
            predictions, config = _detect(
                spec, bars, leg_atr=selected_leg, version=args.version
            )
        classified = _reclassify(predictions, config, selected_prominence)
        final_rows.append(
            _evaluate_sample(
                spec,
                bars,
                labels,
                classified,
                config,
                version=args.version,
            )
        )

    # The frozen baseline is measured on the same split after selection, solely
    # for the before/after report. It cannot affect chosen parameters.
    baseline_rows: list[dict[str, Any]] = []
    for spec in specs:
        bars, labels, _ = samples[spec.id]
        baseline_predictions, baseline_config = _detect_configured(
            spec, bars, version=args.baseline_version
        )
        baseline_rows.append(
            _evaluate_sample(
                spec,
                bars,
                labels,
                baseline_predictions,
                baseline_config,
                version=args.baseline_version,
            )
        )

    train_rows = [row for row in final_rows if row["split"].upper() == "TRAIN"]
    validation_rows = [
        row for row in final_rows if row["split"].upper() == "VALIDATION"
    ]
    baseline_train_rows = [
        row for row in baseline_rows if row["split"].upper() == "TRAIN"
    ]
    baseline_validation_rows = [
        row for row in baseline_rows if row["split"].upper() == "VALIDATION"
    ]
    tuned_all = _aggregate(final_rows)
    baseline_all = _aggregate(baseline_rows)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "engine_version": args.version,
        "baseline_version": args.baseline_version,
        "benchmark": "XAUUSD_H1_AI_ASSISTED_EXPERT_DRAFT",
        "warning": "No locked TEST split exists; do not treat these metrics as production certification.",
        "selection_policy": {
            "location": "max TRAIN F1 subject to TRAIN recall floor; VALIDATION unseen during selection",
            "classification": "max TRAIN macro Major External F1",
            "train_recall_floor": args.train_recall_floor,
        },
        "selected": {
            "leg_min_atr_multiple": selected_leg,
            "structural_prominence_atr": selected_prominence,
        },
        "location_grid": location_grid,
        "classification_grid": classification_grid,
        "baseline": {
            "train": _aggregate(baseline_train_rows),
            "validation": _aggregate(baseline_validation_rows),
            "all_development": baseline_all,
            "by_regime": _aggregate_by_regime(baseline_rows),
            "predicted_type_errors": _aggregate_predicted_type_errors(baseline_rows),
        },
        "results": {
            "train": _aggregate(train_rows),
            "validation": _aggregate(validation_rows),
            "all_development": tuned_all,
            "by_regime": _aggregate_by_regime(final_rows),
            "predicted_type_errors": _aggregate_predicted_type_errors(final_rows),
        },
        "improvement": {
            "false_positive_reduction": baseline_all["false_positives"]
            - tuned_all["false_positives"],
            "false_positive_reduction_pct": round(
                100.0
                * (baseline_all["false_positives"] - tuned_all["false_positives"])
                / baseline_all["false_positives"],
                3,
            )
            if baseline_all["false_positives"]
            else 0.0,
            "f1_gain": round(tuned_all["f1"] - baseline_all["f1"], 6),
            "precision_gain": round(
                tuned_all["precision"] - baseline_all["precision"], 6
            ),
            "recall_change": round(tuned_all["recall"] - baseline_all["recall"], 6),
            "prediction_reduction": baseline_all["predicted"] - tuned_all["predicted"],
        },
        "baseline_per_sample": baseline_rows,
        "per_sample": final_rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload["selected"], indent=2))
    print(
        json.dumps(
            {
                "train": payload["results"]["train"],
                "validation": payload["results"]["validation"],
                "all_development": payload["results"]["all_development"],
                "improvement": payload["improvement"],
            },
            indent=2,
        )
    )
    print(f"Report: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

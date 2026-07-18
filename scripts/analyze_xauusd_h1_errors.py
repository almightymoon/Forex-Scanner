#!/usr/bin/env python3
"""Produce detailed XAUUSD H1 swing-location and hierarchy error analysis.

This script does not tune or modify the detector. It freezes the configured
v2.1 profile, evaluates every development sample, and separates:

- location false positives
- location false negatives
- tier-only errors
- scope-only errors
- combined tier-and-scope errors
- errors by sample, regime, and predicted/true swing type
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from swing_engine.datasets import load_manifest
from swing_engine.models import BenchmarkLabel, DetectedSwing

DEFAULT_MANIFEST = (
    REPO_ROOT
    / "benchmarks"
    / "datasets"
    / "XAUUSD_H1.human.manifest.json"
)
DEFAULT_JSON = (
    REPO_ROOT
    / "benchmarks"
    / "reports"
    / "XAUUSD_H1_v2_1_error_analysis.json"
)
DEFAULT_MARKDOWN = (
    REPO_ROOT
    / "benchmarks"
    / "reports"
    / "XAUUSD_H1_v2_1_error_analysis.md"
)


def _load_tuning_module():
    path = REPO_ROOT / "scripts" / "tune_xauusd_h1.py"
    spec = importlib.util.spec_from_file_location("fxn_tune_xauusd_h1", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load tuning module: {path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


TUNER = _load_tuning_module()


def _type_name(tier: str, scope: str, direction: str) -> str:
    return f"{tier}_{scope}_{direction}"


def _number(value: Any) -> float | int | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return round(number, 6)


def _prediction_snapshot(swing: DetectedSwing) -> dict[str, Any]:
    metadata = swing.metadata

    return {
        "pivot_index": swing.pivot_index,
        "confirmation_index": swing.confirmation_index,
        "timestamp": swing.timestamp.isoformat(),
        "price": swing.price,
        "direction": swing.direction.value,
        "tier": swing.tier.value,
        "scope": swing.scope.value,
        "type": swing.type_label,
        "strength": swing.strength,
        "quality_score": round(swing.quality_score, 3),
        "confidence": round(swing.confidence, 6),
        "confirmation_delay": swing.confirmation_delay,
        "features": {
            "leg_atr": _number(metadata.get("leg_atr")),
            "structural_reversal_atr": _number(
                metadata.get("structural_reversal_atr")
            ),
            "structural_prominence_atr": _number(
                metadata.get("structural_prominence_atr")
            ),
            "tier_score": _number(metadata.get("tier_score")),
            "available_index": metadata.get("available_index"),
            "structural_confirmation_index": metadata.get(
                "structural_confirmation_index"
            ),
        },
    }


def _label_snapshot(label: BenchmarkLabel) -> dict[str, Any]:
    return {
        "label_id": label.label_id,
        "sample_id": label.sample_id,
        "pivot_index": label.pivot_index,
        "confirmed_at_index": label.confirmed_at_index,
        "timestamp": label.timestamp.isoformat(),
        "price": label.price,
        "direction": label.direction.value,
        "tier": label.tier.value,
        "scope": label.scope.value,
        "type": _type_name(
            label.tier.value,
            label.scope.value,
            label.direction.value,
        ),
        "strength": label.strength,
        "quality_score": label.quality_score,
        "confidence": label.confidence,
        "tags": list(label.tags),
        "notes": label.notes,
    }


def _safe_div(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def _f1(precision: float, recall: float) -> float:
    return (
        2.0 * precision * recall / (precision + recall)
        if precision + recall
        else 0.0
    )


def _semantic_error_kind(pair: dict[str, Any]) -> str:
    tier_match = bool(pair["tier_match"])
    scope_match = bool(pair["scope_match"])

    if not tier_match and not scope_match:
        return "TIER_AND_SCOPE"
    if not tier_match:
        return "TIER_ONLY"
    if not scope_match:
        return "SCOPE_ONLY"
    return "NONE"


def _analyze_sample(
    spec,
    *,
    manifest: Path,
    version: str,
) -> dict[str, Any]:
    bars, labels = TUNER._load_sample(spec, manifest)
    predictions, config = TUNER._detect_configured(
        spec,
        bars,
        version=version,
    )

    evaluation = TUNER._evaluate_sample(
        spec,
        bars,
        labels,
        predictions,
        config,
        version=version,
    )

    pairs = evaluation["matched_pairs"]

    prediction_map = {
        (swing.pivot_index, swing.direction.value): swing
        for swing in predictions
    }
    label_map = {
        (label.pivot_index, label.direction.value): label
        for label in labels
    }

    matched_prediction_keys = {
        (int(pair["predicted_index"]), pair["predicted_direction"])
        for pair in pairs
    }
    matched_label_keys = {
        (int(pair["ground_truth_index"]), pair["ground_truth_direction"])
        for pair in pairs
    }

    false_positives = [
        _prediction_snapshot(swing)
        for key, swing in prediction_map.items()
        if key not in matched_prediction_keys
    ]
    false_negatives = [
        _label_snapshot(label)
        for key, label in label_map.items()
        if key not in matched_label_keys
    ]

    semantic_errors: list[dict[str, Any]] = []
    semantic_confusion: Counter[str] = Counter()

    for pair in pairs:
        if pair["full_semantic_match"]:
            continue

        predicted_key = (
            int(pair["predicted_index"]),
            pair["predicted_direction"],
        )
        label_key = (
            int(pair["ground_truth_index"]),
            pair["ground_truth_direction"],
        )

        prediction = prediction_map[predicted_key]
        label = label_map[label_key]

        predicted_type = prediction.type_label
        truth_type = _type_name(
            label.tier.value,
            label.scope.value,
            label.direction.value,
        )
        error_kind = _semantic_error_kind(pair)

        semantic_confusion[f"{truth_type}->{predicted_type}"] += 1
        semantic_errors.append(
            {
                "error_kind": error_kind,
                "truth": _label_snapshot(label),
                "prediction": _prediction_snapshot(prediction),
                "time_error_bars": pair["time_error_bars"],
                "price_error_pips": pair["price_error_pips"],
                "relative_detection_delay_bars": pair[
                    "relative_detection_delay_bars"
                ],
            }
        )

    semantic_tp = sum(
        1 for pair in pairs if pair["full_semantic_match"]
    )
    semantic_fp = len(predictions) - semantic_tp
    semantic_fn = len(labels) - semantic_tp

    semantic_precision = _safe_div(
        semantic_tp,
        semantic_tp + semantic_fp,
    )
    semantic_recall = _safe_div(
        semantic_tp,
        semantic_tp + semantic_fn,
    )

    return {
        "dataset_id": spec.id,
        "sample_id": spec.sample_id,
        "split": spec.split,
        "regime": spec.regime,
        "bar_count": len(bars),
        "ground_truth_count": len(labels),
        "prediction_count": len(predictions),
        "location": {
            "true_positives": evaluation["true_positives"],
            "false_positives": evaluation["false_positives"],
            "false_negatives": evaluation["false_negatives"],
            "precision": evaluation["precision"],
            "recall": evaluation["recall"],
            "f1": evaluation["f1_score"],
        },
        "semantic": {
            "true_positives": semantic_tp,
            "false_positives": semantic_fp,
            "false_negatives": semantic_fn,
            "precision": round(semantic_precision, 6),
            "recall": round(semantic_recall, 6),
            "f1": round(
                _f1(semantic_precision, semantic_recall),
                6,
            ),
            "tier_accuracy_on_location_matches": evaluation[
                "tier_accuracy"
            ],
            "scope_accuracy_on_location_matches": evaluation[
                "scope_accuracy"
            ],
            "major_external_f1": evaluation[
                "major_external_f1"
            ],
        },
        "semantic_confusion": dict(
            sorted(
                semantic_confusion.items(),
                key=lambda item: (-item[1], item[0]),
            )
        ),
        "semantic_errors": semantic_errors,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
    }


def _aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    predictions = sum(row["prediction_count"] for row in rows)
    truth = sum(row["ground_truth_count"] for row in rows)

    location_tp = sum(
        row["location"]["true_positives"] for row in rows
    )
    location_fp = sum(
        row["location"]["false_positives"] for row in rows
    )
    location_fn = sum(
        row["location"]["false_negatives"] for row in rows
    )

    location_precision = _safe_div(
        location_tp,
        location_tp + location_fp,
    )
    location_recall = _safe_div(
        location_tp,
        location_tp + location_fn,
    )

    semantic_tp = sum(
        row["semantic"]["true_positives"] for row in rows
    )
    semantic_fp = predictions - semantic_tp
    semantic_fn = truth - semantic_tp

    semantic_precision = _safe_div(
        semantic_tp,
        semantic_tp + semantic_fp,
    )
    semantic_recall = _safe_div(
        semantic_tp,
        semantic_tp + semantic_fn,
    )

    semantic_confusion: Counter[str] = Counter()
    fp_types: Counter[str] = Counter()
    fn_types: Counter[str] = Counter()
    error_kinds: Counter[str] = Counter()

    matched_count = 0
    tier_correct = 0
    scope_correct = 0

    for row in rows:
        semantic_confusion.update(row["semantic_confusion"])
        fp_types.update(
            item["type"] for item in row["false_positives"]
        )
        fn_types.update(
            item["type"] for item in row["false_negatives"]
        )
        error_kinds.update(
            item["error_kind"]
            for item in row["semantic_errors"]
        )

        sample_matches = row["location"]["true_positives"]
        matched_count += sample_matches
        tier_correct += round(
            row["semantic"]["tier_accuracy_on_location_matches"]
            * sample_matches
        )
        scope_correct += round(
            row["semantic"]["scope_accuracy_on_location_matches"]
            * sample_matches
        )

    return {
        "datasets": len(rows),
        "predicted": predictions,
        "ground_truth": truth,
        "location": {
            "true_positives": location_tp,
            "false_positives": location_fp,
            "false_negatives": location_fn,
            "precision": round(location_precision, 6),
            "recall": round(location_recall, 6),
            "f1": round(
                _f1(location_precision, location_recall),
                6,
            ),
        },
        "semantic": {
            "true_positives": semantic_tp,
            "false_positives": semantic_fp,
            "false_negatives": semantic_fn,
            "precision": round(semantic_precision, 6),
            "recall": round(semantic_recall, 6),
            "f1": round(
                _f1(semantic_precision, semantic_recall),
                6,
            ),
            "tier_accuracy_on_location_matches": round(
                _safe_div(tier_correct, matched_count),
                6,
            ),
            "scope_accuracy_on_location_matches": round(
                _safe_div(scope_correct, matched_count),
                6,
            ),
        },
        "semantic_error_kinds": dict(
            sorted(
                error_kinds.items(),
                key=lambda item: (-item[1], item[0]),
            )
        ),
        "semantic_confusion": dict(
            sorted(
                semantic_confusion.items(),
                key=lambda item: (-item[1], item[0]),
            )
        ),
        "false_positive_types": dict(
            sorted(
                fp_types.items(),
                key=lambda item: (-item[1], item[0]),
            )
        ),
        "false_negative_types": dict(
            sorted(
                fn_types.items(),
                key=lambda item: (-item[1], item[0]),
            )
        ),
    }


def _by_regime(
    rows: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["regime"])].append(row)

    return {
        regime: _aggregate(items)
        for regime, items in sorted(grouped.items())
    }


def _hotspots(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    for row in rows:
        semantic_mismatches = len(row["semantic_errors"])
        location_errors = (
            row["location"]["false_positives"]
            + row["location"]["false_negatives"]
        )

        items.append(
            {
                "dataset_id": row["dataset_id"],
                "sample_id": row["sample_id"],
                "split": row["split"],
                "regime": row["regime"],
                "location_false_positives": row[
                    "location"
                ]["false_positives"],
                "location_false_negatives": row[
                    "location"
                ]["false_negatives"],
                "semantic_mismatches": semantic_mismatches,
                "total_error_events": (
                    location_errors + semantic_mismatches
                ),
                "location_f1": row["location"]["f1"],
                "semantic_f1": row["semantic"]["f1"],
                "major_external_f1": row[
                    "semantic"
                ]["major_external_f1"],
            }
        )

    return sorted(
        items,
        key=lambda item: (
            item["total_error_events"],
            item["location_false_negatives"],
            item["semantic_mismatches"],
        ),
        reverse=True,
    )


def _markdown(payload: dict[str, Any]) -> str:
    overall = payload["overall"]
    location = overall["location"]
    semantic = overall["semantic"]

    lines = [
        "# XAUUSD H1 Swing Error Analysis",
        "",
        f"- Engine version: `{payload['engine_version']}`",
        f"- Generated: `{payload['generated_at']}`",
        f"- Samples: {overall['datasets']}",
        f"- Predictions: {overall['predicted']}",
        f"- Ground-truth swings: {overall['ground_truth']}",
        "",
        "## Location performance",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Precision | {location['precision']:.4f} |",
        f"| Recall | {location['recall']:.4f} |",
        f"| F1 | {location['f1']:.4f} |",
        f"| False positives | {location['false_positives']} |",
        f"| False negatives | {location['false_negatives']} |",
        "",
        "## Full semantic performance",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Precision | {semantic['precision']:.4f} |",
        f"| Recall | {semantic['recall']:.4f} |",
        f"| F1 | {semantic['f1']:.4f} |",
        (
            "| Tier accuracy on matched pivots | "
            f"{semantic['tier_accuracy_on_location_matches']:.4f} |"
        ),
        (
            "| Scope accuracy on matched pivots | "
            f"{semantic['scope_accuracy_on_location_matches']:.4f} |"
        ),
        "",
        "## Error hotspots",
        "",
        "| Sample | Split | Regime | FP | FN | Semantic | Total |",
        "|---|---|---|---:|---:|---:|---:|",
    ]

    for item in payload["hotspots"]:
        lines.append(
            "| {dataset_id} | {split} | {regime} | "
            "{location_false_positives} | "
            "{location_false_negatives} | "
            "{semantic_mismatches} | "
            "{total_error_events} |".format(**item)
        )

    lines.extend(
        [
            "",
            "## Semantic confusion",
            "",
            "| Truth → Prediction | Count |",
          "|---|---:|",
        ]
    )

    for key, count in overall["semantic_confusion"].items():
        lines.append(f"| `{key}` | {count} |")

    lines.extend(
        [
            "",
            "## Error classes",
            "",
            "| Error | Count |",
            "|---|---:|",
        ]
    )

    for key, count in overall["semantic_error_kinds"].items():
        lines.append(f"| {key} | {count} |")

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
    )
    parser.add_argument("--version", default="2.1.0")
    parser.add_argument(
        "--output-json",
        type=Path,
        default=DEFAULT_JSON,
    )
    parser.add_argument(
        "--output-markdown",
        type=Path,
        default=DEFAULT_MARKDOWN,
    )
    args = parser.parse_args()

    specs = load_manifest(args.manifest)

    if any(spec.split.upper() == "TEST" for spec in specs):
        raise SystemExit(
            "Error analysis refuses to inspect locked TEST samples."
        )

    rows = [
        _analyze_sample(
            spec,
            manifest=args.manifest,
            version=args.version,
        )
        for spec in specs
    ]

    train_rows = [
        row for row in rows if row["split"].upper() == "TRAIN"
    ]
    validation_rows = [
        row
        for row in rows
        if row["split"].upper() == "VALIDATION"
    ]

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(
            timespec="seconds"
        ),
        "engine_version": args.version,
        "benchmark": "XAUUSD_H1_AI_ASSISTED_EXPERT_DRAFT",
        "warning": (
            "No locked TEST split exists. This is development "
            "error analysis, not production certification."
        ),
        "overall": _aggregate(rows),
        "train": _aggregate(train_rows),
        "validation": _aggregate(validation_rows),
        "by_regime": _by_regime(rows),
        "hotspots": _hotspots(rows),
        "per_sample": rows,
    }

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_markdown.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    args.output_json.write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )
    args.output_markdown.write_text(
        _markdown(payload),
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "overall": payload["overall"],
                "train": payload["train"],
                "validation": payload["validation"],
                "top_hotspots": payload["hotspots"][:5],
            },
            indent=2,
        )
    )
    print(f"JSON report: {args.output_json}")
    print(f"Markdown report: {args.output_markdown}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""TRAIN-only semantic failure audit for v2.4 development (samples 001-008).

DEVELOPMENT_ONLY. Uses XAUUSD_H1_001..008 exclusively. Does not inspect or use
VALIDATION 009-012, 2026H1, AI-draft windows, or post-2026H1 quarantine data.
Produces no production or release decision.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from swing_engine.datasets import load_manifest  # noqa: E402
from swing_engine.models import SwingScope, SwingTier  # noqa: E402


MANIFEST = ROOT / "benchmarks/datasets/XAUUSD_H1.human.manifest.json"
OUTPUT = ROOT / "benchmarks/reports/XAUUSD_H1_v2_4_semantic_failure_audit.json"

TRAIN_IDS = tuple(f"XAUUSD_H1_{n:03d}" for n in range(1, 9))
FORBIDDEN_IDS = tuple(f"XAUUSD_H1_{n:03d}" for n in range(9, 13))
VERSION = "2.3.0"
HYPOTHESIS_OUTPUT = (
    ROOT / "benchmarks/reports/XAUUSD_H1_v2_4_semantic_hypothesis.json"
)

THRESHOLD_EXPERIMENT = {
    "experiment_label": "V2_4_THRESHOLD_ONLY_HYPOTHESIS",
    "engine_version": "2.3.0",
    "hierarchy_reversal_atr_override": 4.25,
    "active_v2_4_profile": False,
    "accepted_candidate": False,
}


def load_helpers():
    path = ROOT / "scripts/tune_xauusd_h1_hierarchy.py"
    spec = importlib.util.spec_from_file_location(
        "fxn_v24_semantic_audit_helpers", path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


HELPERS = load_helpers()


def meta_get(swing, *keys: str) -> Any:
    metadata = swing.metadata or {}
    for key in keys:
        if key in metadata and metadata[key] is not None:
            return metadata[key]
    return None


def feature_snapshot(pred, truth) -> dict[str, Any]:
    return {
        "pivot_index": pred.pivot_index,
        "direction": pred.direction.value,
        "predicted_tier": pred.tier.value,
        "predicted_scope": pred.scope.value,
        "truth_tier": truth.tier.value,
        "truth_scope": truth.scope.value,
        "hierarchy_state": (
            pred.hierarchy_state.value if pred.hierarchy_state else None
        ),
        "confirmation_index": pred.confirmation_index,
        "hierarchy_confirmation_index": pred.hierarchy_confirmation_index,
        "available_index": meta_get(
            pred, "available_index", "hierarchy_available_index"
        ),
        "structural_confirmation_index": meta_get(
            pred, "structural_confirmation_index"
        ),
        "structural_prominence_atr": meta_get(
            pred, "structural_prominence_atr", "hierarchy_pending_prominence_atr"
        ),
        "hierarchy_reversal_atr": meta_get(pred, "hierarchy_reversal_atr"),
        "hierarchy_reason": meta_get(pred, "hierarchy_reason"),
        "hierarchy_anchor_pivot_index": meta_get(
            pred, "hierarchy_anchor_pivot_index"
        ),
        "hierarchy_reversal_pivot_index": meta_get(
            pred, "hierarchy_reversal_pivot_index"
        ),
        "hierarchy_superseded_by_index": meta_get(
            pred, "hierarchy_superseded_by_index"
        ),
        "hierarchy_was_provisional": meta_get(pred, "hierarchy_was_provisional"),
        "confirmation_delay": pred.confirmation_delay,
    }


def classify_match(pred, truth) -> str:
    tier_ok = pred.tier is truth.tier
    scope_ok = pred.scope is truth.scope
    if tier_ok and scope_ok:
        return "semantic_correct"
    if (not tier_ok) and scope_ok:
        return "wrong_tier_only"
    if tier_ok and (not scope_ok):
        return "wrong_scope_only"
    return "wrong_tier_and_scope"


def is_major_external(tier, scope) -> bool:
    return tier is SwingTier.MAJOR and scope is SwingScope.EXTERNAL


def main() -> int:
    specs = [
        spec
        for spec in load_manifest(MANIFEST)
        if spec.id in TRAIN_IDS and spec.split.upper() == "TRAIN"
    ]
    if [spec.id for spec in specs] != list(TRAIN_IDS):
        raise SystemExit(
            "REFUSED: expected TRAIN samples 001-008 only, "
            f"got {[spec.id for spec in specs]}"
        )
    for forbidden in FORBIDDEN_IDS:
        if any(spec.id == forbidden for spec in specs):
            raise SystemExit(f"REFUSED: validation sample {forbidden} leaked")

    location_tp = location_fp = location_fn = 0
    predicted_me = truth_me = me_tp = me_fp = me_fn = 0
    semantic_classes: Counter[str] = Counter()
    tier_confusion: Counter[str] = Counter()
    scope_confusion: Counter[str] = Counter()
    hierarchy_states: Counter[str] = Counter()
    confirmation_delays: list[int] = []
    wrong_by_hierarchy: dict[str, Counter[str]] = defaultdict(Counter)
    per_sample: list[dict[str, Any]] = []
    matched_cases: list[dict[str, Any]] = []
    mismatched_cases: list[dict[str, Any]] = []

    semantic_tp_total = 0
    location_match_total = 0

    for spec in specs:
        bars, labels = HELPERS._load_sample(spec, MANIFEST)
        predictions, config = HELPERS._detect(spec, bars, version=VERSION)
        row = HELPERS._evaluate_sample(
            spec,
            bars,
            labels,
            predictions,
            config,
            version=VERSION,
        )

        evaluation = config.evaluation
        if spec.evaluation_tolerance_bars:
            from dataclasses import replace

            evaluation = replace(
                evaluation,
                index_match_tolerance_bars=spec.evaluation_tolerance_bars,
            )
        from dataclasses import replace as dc_replace
        from swing_engine.evaluation import SwingBenchmarkEvaluator

        report = SwingBenchmarkEvaluator(
            dc_replace(config, evaluation=evaluation)
        ).evaluate(
            predictions,
            labels,
            spec.symbol,
            engine_version=VERSION,
            benchmark_version="XAUUSD_H1_V2_4_SEMANTIC_AUDIT",
        )

        sample_classes: Counter[str] = Counter()
        sample_matches = 0
        sample_semantic_tp = 0

        confirmed = [s for s in predictions if s.confirmed]
        pred_by_key = {
            (s.pivot_index, s.direction.value): s for s in confirmed
        }
        truth_by_key = {
            (lab.pivot_index, lab.direction.value): lab for lab in labels
        }
        # Prefer exact pivot index from matched_pairs; fall back to direction+near
        matched_pred_keys: set[tuple[int, str]] = set()
        matched_truth_keys: set[tuple[int, str]] = set()

        for pair in report.matched_pairs:
            pred_key = (
                int(pair["predicted_index"]),
                str(pair["predicted_direction"]),
            )
            truth_key = (
                int(pair["ground_truth_index"]),
                str(pair["ground_truth_direction"]),
            )
            pred = pred_by_key.get(pred_key)
            truth = truth_by_key.get(truth_key)
            if pred is None or truth is None:
                # Tolerance match: find nearest confirmed prediction
                pred = min(
                    (
                        s
                        for s in confirmed
                        if s.direction.value == pair["predicted_direction"]
                    ),
                    key=lambda s: abs(s.pivot_index - int(pair["predicted_index"])),
                    default=None,
                )
                truth = min(
                    (
                        lab
                        for lab in labels
                        if lab.direction.value == pair["ground_truth_direction"]
                    ),
                    key=lambda lab: abs(
                        lab.pivot_index - int(pair["ground_truth_index"])
                    ),
                    default=None,
                )
            if pred is None or truth is None:
                continue

            matched_pred_keys.add((pred.pivot_index, pred.direction.value))
            matched_truth_keys.add((truth.pivot_index, truth.direction.value))

            kind = classify_match(pred, truth)
            sample_classes[kind] += 1
            semantic_classes[kind] += 1
            sample_matches += 1
            location_match_total += 1
            if kind == "semantic_correct":
                sample_semantic_tp += 1
                semantic_tp_total += 1

            tier_confusion[
                f"{truth.tier.value}->{pred.tier.value}"
            ] += 1
            scope_confusion[
                f"{truth.scope.value}->{pred.scope.value}"
            ] += 1

            state = (
                pred.hierarchy_state.value
                if pred.hierarchy_state
                else "NONE"
            )
            hierarchy_states[state] += 1
            if pred.confirmation_delay is not None:
                confirmation_delays.append(int(pred.confirmation_delay))

            case = {
                "sample_id": spec.id,
                "semantic_class": kind,
                **feature_snapshot(pred, truth),
            }
            if kind == "semantic_correct":
                matched_cases.append(case)
            else:
                mismatched_cases.append(case)
                wrong_by_hierarchy[state][kind] += 1

            if is_major_external(pred.tier, pred.scope):
                predicted_me += 1
            if is_major_external(truth.tier, truth.scope):
                truth_me += 1
            if is_major_external(pred.tier, pred.scope) and is_major_external(
                truth.tier, truth.scope
            ):
                me_tp += 1
            if is_major_external(pred.tier, pred.scope) and not is_major_external(
                truth.tier, truth.scope
            ):
                me_fp += 1
            if is_major_external(truth.tier, truth.scope) and not is_major_external(
                pred.tier, pred.scope
            ):
                me_fn += 1

        for pred in confirmed:
            key = (pred.pivot_index, pred.direction.value)
            if key in matched_pred_keys:
                continue
            if is_major_external(pred.tier, pred.scope):
                predicted_me += 1
                me_fp += 1
            state = (
                pred.hierarchy_state.value
                if pred.hierarchy_state
                else "NONE"
            )
            hierarchy_states[state] += 1

        for truth in labels:
            key = (truth.pivot_index, truth.direction.value)
            if key in matched_truth_keys:
                continue
            if is_major_external(truth.tier, truth.scope):
                truth_me += 1
                me_fn += 1

        location_tp += int(report.true_positives)
        location_fp += int(report.false_positives)
        location_fn += int(report.false_negatives)

        per_sample.append(
            {
                "sample_id": spec.id,
                "split": "TRAIN",
                "location": {
                    "true_positives": report.true_positives,
                    "false_positives": report.false_positives,
                    "false_negatives": report.false_negatives,
                    "precision": report.precision,
                    "recall": report.recall,
                    "f1": report.f1_score,
                },
                "semantic": {
                    "true_positives": sample_semantic_tp,
                    "location_matches": sample_matches,
                    "precision": (
                        sample_semantic_tp / len(confirmed)
                        if confirmed
                        else 0.0
                    ),
                    "recall": (
                        sample_semantic_tp / len(labels) if labels else 0.0
                    ),
                    "f1": row["semantic_f1"],
                    "tier_accuracy": row["tier_accuracy"],
                    "scope_accuracy": row["scope_accuracy"],
                    "classes": dict(sample_classes),
                },
                "major_external": {
                    "predicted": row["major_external_predicted"],
                    "truth": row["major_external_truth"],
                    "true_positives": row["major_external_true_positives"],
                },
                "hierarchy_states": row.get("hierarchy_states", {}),
            }
        )

    def f1(precision: float, recall: float) -> float:
        if precision + recall == 0:
            return 0.0
        return 2.0 * precision * recall / (precision + recall)

    loc_p = (
        location_tp / (location_tp + location_fp)
        if location_tp + location_fp
        else 0.0
    )
    loc_r = (
        location_tp / (location_tp + location_fn)
        if location_tp + location_fn
        else 0.0
    )
    sem_p = (
        semantic_tp_total / (location_tp + location_fp)
        if location_tp + location_fp
        else 0.0
    )
    sem_r = (
        semantic_tp_total / (location_tp + location_fn)
        if location_tp + location_fn
        else 0.0
    )
    me_p = me_tp / predicted_me if predicted_me else 0.0
    me_r = me_tp / truth_me if truth_me else 0.0

    delay_hist = Counter(confirmation_delays)

    # Dominant wrong-scope pattern among mismatches
    scope_only = [
        case
        for case in mismatched_cases
        if case["semantic_class"] == "wrong_scope_only"
    ]
    major_internal_truth = [
        case
        for case in mismatched_cases
        if case["truth_tier"] == "MAJOR"
        and case["truth_scope"] == "INTERNAL"
        and case["predicted_tier"] == "MAJOR"
        and case["predicted_scope"] == "EXTERNAL"
    ]
    minor_as_major_external = [
        case
        for case in mismatched_cases
        if case["truth_tier"] == "MINOR"
        and case["predicted_tier"] == "MAJOR"
        and case["predicted_scope"] == "EXTERNAL"
    ]

    report = {
        "classification": "DEVELOPMENT_ONLY",
        "scope": "TRAIN_001_008_ONLY",
        "decision_status": "NOT_A_RELEASE_DECISION",
        "purpose": "v2.4 semantic failure audit",
        "viable_v2_4_development_candidate": False,
        "active_v2_4_profile": False,
        "latest_version": "2.3.0",
        "threshold_only_experiment": THRESHOLD_EXPERIMENT,
        "engine_version": VERSION,
        "samples": list(TRAIN_IDS),
        "sample_policy": {
            "used": list(TRAIN_IDS),
            "split": "TRAIN",
            "forbidden_validation_samples": list(FORBIDDEN_IDS),
            "forbidden_other": [
                "XAUUSD_H1_2026H1_*",
                "retrospective AI-draft windows",
                "post-2026H1 quarantine",
            ],
            "no_holdout_inference": True,
            "no_production_or_release_decision": True,
            "excluded_datasets_not_used": True,
        },
        "generated_at_utc": datetime.now(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
        "aggregate": {
            "location": {
                "true_positives": location_tp,
                "false_positives": location_fp,
                "false_negatives": location_fn,
                "precision": round(loc_p, 6),
                "recall": round(loc_r, 6),
                "f1": round(f1(loc_p, loc_r), 6),
            },
            "semantic": {
                "classes": dict(semantic_classes),
                "location_matches": location_match_total,
                "semantic_correct": semantic_classes["semantic_correct"],
                "precision": round(sem_p, 6),
                "recall": round(sem_r, 6),
                "f1": round(f1(sem_p, sem_r), 6),
            },
            "major_external": {
                "predicted": predicted_me,
                "truth": truth_me,
                "true_positives": me_tp,
                "false_positives": me_fp,
                "false_negatives": me_fn,
                "precision": round(me_p, 6),
                "recall": round(me_r, 6),
                "f1": round(f1(me_p, me_r), 6),
            },
            "tier_confusion": dict(sorted(tier_confusion.items())),
            "scope_confusion": dict(sorted(scope_confusion.items())),
            "predicted_hierarchy_state_distribution": dict(
                sorted(hierarchy_states.items())
            ),
            "confirmation_delay_distribution": {
                str(k): v for k, v in sorted(delay_hist.items())
            },
            "wrong_semantic_by_hierarchy_state": {
                state: dict(counter)
                for state, counter in sorted(wrong_by_hierarchy.items())
            },
            "pattern_counts": {
                "wrong_scope_only": len(scope_only),
                "major_truth_internal_predicted_external": len(
                    major_internal_truth
                ),
                "minor_truth_predicted_major_external": len(
                    minor_as_major_external
                ),
            },
        },
        "per_sample": per_sample,
        "mismatched_cases": mismatched_cases,
        "matched_case_count": len(matched_cases),
        "warning": (
            "DEVELOPMENT_ONLY audit on TRAIN samples 001-008. "
            "No holdout inference. No production or release decision. "
            "No active 2.4.0 profile; v2.3 remains latest."
        ),
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    me_truth_as_minor = [
        case
        for case in mismatched_cases
        if case.get("truth_tier") == "MAJOR"
        and case.get("truth_scope") == "EXTERNAL"
        and case.get("predicted_tier") == "MINOR"
        and case.get("predicted_scope") == "INTERNAL"
    ]
    insufficient = [
        case
        for case in me_truth_as_minor
        if (case.get("hierarchy_reason") or "")
        == "insufficient_hierarchy_reversal"
    ]
    hypothesis = {
        "classification": "DEVELOPMENT_ONLY",
        "scope": "TRAIN_001_008_ONLY",
        "decision_status": "NOT_A_RELEASE_DECISION",
        "viable_v2_4_development_candidate": False,
        "active_v2_4_profile": False,
        "latest_version": "2.3.0",
        "threshold_only_experiment": THRESHOLD_EXPERIMENT,
        "selected_using": "TRAIN XAUUSD_H1_001 through XAUUSD_H1_008 only",
        "no_holdout_inference": True,
        "excluded_datasets_not_used": True,
        "observed_failure_mode": (
            "True MAJOR/EXTERNAL swings remain MINOR/INTERNAL because opposite "
            "hierarchy reversals of roughly 3.8-4.8 ATR fail the fixed "
            "hierarchy_reversal_atr=5.0 gate "
            "(hierarchy_reason=insufficient_hierarchy_reversal)."
        ),
        "supporting_counts": {
            "location_matches": location_match_total,
            "semantic_correct": semantic_classes["semantic_correct"],
            "major_external_truth_predicted_minor_internal": len(
                me_truth_as_minor
            ),
            "insufficient_hierarchy_reversal_among_those": len(insufficient),
            "v2_3_semantic_f1": round(f1(sem_p, sem_r), 6),
            "v2_3_major_external_f1": round(f1(me_p, me_r), 6),
            "v2_3_major_external_precision": round(me_p, 6),
            "v2_3_major_external_recall": round(me_r, 6),
        },
        "proposed_minimal_change_was": (
            "Development version 2.4.0 lowering hierarchy_reversal_atr "
            "5.00 -> 4.25 (threshold-only). Evaluated and refused."
        ),
        "final_disposition": (
            "REFUSED: threshold-only 4.25 fails ME precision floor; "
            "predeclared structural Rules A-C also fail TRAIN acceptance. "
            "No active 2.4.0 profile. v2.3 remains latest."
        ),
        "explicit_statement": (
            "Hypothesis and negative result use TRAIN samples "
            "XAUUSD_H1_001 through XAUUSD_H1_008 only. Validation 009-012, "
            "2026H1, retrospective AI-draft windows, and post-2026H1 "
            "quarantine data were not used."
        ),
    }
    HYPOTHESIS_OUTPUT.write_text(
        json.dumps(hypothesis, indent=2) + "\n", encoding="utf-8"
    )

    print(
        json.dumps(
            {
                "output": str(OUTPUT),
                "hypothesis_output": str(HYPOTHESIS_OUTPUT),
                "viable_v2_4_development_candidate": False,
                "semantic_classes": dict(semantic_classes),
                "location_f1": report["aggregate"]["location"]["f1"],
                "semantic_f1": report["aggregate"]["semantic"]["f1"],
                "major_external_f1": report["aggregate"]["major_external"]["f1"],
                "pattern_counts": report["aggregate"]["pattern_counts"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

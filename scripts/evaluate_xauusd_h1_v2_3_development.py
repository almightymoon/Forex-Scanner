#!/usr/bin/env python3
"""Compare frozen v2.2 and candidate v2.3 on exposed TRAIN samples only.

Loads candle and label material for XAUUSD_H1_001 through 008.
Original VALIDATION 009-012 and the historical locked TEST are not loaded.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from swing_engine.datasets import load_manifest  # noqa: E402


MANIFEST = (
    ROOT
    / "benchmarks"
    / "datasets"
    / "XAUUSD_H1.human.manifest.json"
)

OUTPUT = (
    ROOT
    / "benchmarks"
    / "reports"
    / "XAUUSD_H1_v2_3_development_evaluation.json"
)

DEVELOPMENT_IDS = tuple(
    f"XAUUSD_H1_{number:03d}"
    for number in range(1, 9)
)

UNTOUCHED_VALIDATION_IDS = tuple(
    f"XAUUSD_H1_{number:03d}"
    for number in range(9, 13)
)


def load_hierarchy_evaluator():
    path = (
        ROOT
        / "scripts"
        / "tune_xauusd_h1_hierarchy.py"
    )

    spec = importlib.util.spec_from_file_location(
        "fxn_v23_development_hierarchy_evaluator",
        path,
    )

    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


EVALUATOR = load_hierarchy_evaluator()


def metric(
    payload: dict[str, Any],
    *path: str,
) -> float:
    value: Any = payload

    for key in path:
        value = value[key]

    return float(value)


def delta(
    candidate: dict[str, Any],
    baseline: dict[str, Any],
    *path: str,
) -> float:
    return round(
        metric(candidate, *path)
        - metric(baseline, *path),
        6,
    )


def per_sample_rows(
    baseline_rows: list[dict[str, Any]],
    candidate_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    baseline_by_id = {
        row["dataset_id"]: row
        for row in baseline_rows
    }

    output: list[dict[str, Any]] = []

    for candidate in candidate_rows:
        sample_id = candidate["dataset_id"]
        baseline = baseline_by_id[sample_id]

        baseline_aggregate = EVALUATOR._aggregate(
            [baseline]
        )
        candidate_aggregate = EVALUATOR._aggregate(
            [candidate]
        )

        output.append(
            {
                "dataset_id": sample_id,
                "regime": candidate["regime"],
                "v2_2": {
                    "predicted": baseline["predicted"],
                    "true_positives": baseline["true_positives"],
                    "false_positives": baseline["false_positives"],
                    "false_negatives": baseline["false_negatives"],
                    "location_f1": baseline_aggregate[
                        "location"
                    ]["f1"],
                    "semantic_f1": baseline["semantic_f1"],
                    "tier_accuracy": baseline["tier_accuracy"],
                    "scope_accuracy": baseline["scope_accuracy"],
                    "major_external_predicted": (
                        baseline["major_external_predicted"]
                    ),
                    "major_external_true_positives": (
                        baseline[
                            "major_external_true_positives"
                        ]
                    ),
                },
                "v2_3": {
                    "predicted": candidate["predicted"],
                    "true_positives": candidate["true_positives"],
                    "false_positives": candidate["false_positives"],
                    "false_negatives": candidate["false_negatives"],
                    "location_f1": candidate_aggregate[
                        "location"
                    ]["f1"],
                    "semantic_f1": candidate["semantic_f1"],
                    "tier_accuracy": candidate["tier_accuracy"],
                    "scope_accuracy": candidate["scope_accuracy"],
                    "major_external_predicted": (
                        candidate["major_external_predicted"]
                    ),
                    "major_external_true_positives": (
                        candidate[
                            "major_external_true_positives"
                        ]
                    ),
                },
                "delta": {
                    "predicted": (
                        int(candidate["predicted"])
                        - int(baseline["predicted"])
                    ),
                    "true_positives": (
                        int(candidate["true_positives"])
                        - int(baseline["true_positives"])
                    ),
                    "false_positives": (
                        int(candidate["false_positives"])
                        - int(baseline["false_positives"])
                    ),
                    "false_negatives": (
                        int(candidate["false_negatives"])
                        - int(baseline["false_negatives"])
                    ),
                    "location_f1": round(
                        float(
                            candidate_aggregate[
                                "location"
                            ]["f1"]
                        )
                        - float(
                            baseline_aggregate[
                                "location"
                            ]["f1"]
                        ),
                        6,
                    ),
                    "semantic_f1": round(
                        float(candidate["semantic_f1"])
                        - float(baseline["semantic_f1"]),
                        6,
                    ),
                },
            }
        )

    return output


def main() -> int:
    if "2026h1" in str(MANIFEST).lower():
        raise SystemExit(
            "REFUSED: historical locked TEST manifest supplied"
        )

    specs = load_manifest(MANIFEST)
    spec_by_id = {
        spec.id: spec
        for spec in specs
    }

    missing = (
        set(DEVELOPMENT_IDS)
        - set(spec_by_id)
    )

    if missing:
        raise SystemExit(
            f"Missing development samples: {sorted(missing)}"
        )

    development_specs = [
        spec_by_id[sample_id]
        for sample_id in DEVELOPMENT_IDS
    ]

    if any(
        spec.split.upper() != "TRAIN"
        for spec in development_specs
    ):
        raise SystemExit(
            "REFUSED: development material must be TRAIN"
        )

    if set(DEVELOPMENT_IDS).intersection(
        UNTOUCHED_VALIDATION_IDS
    ):
        raise SystemExit(
            "REFUSED: development/validation overlap"
        )

    test_specs = [
        spec
        for spec in specs
        if spec.split.upper() == "TEST"
    ]

    if test_specs:
        raise SystemExit(
            "REFUSED: manifest contains TEST samples"
        )

    # Only these eight calls load candle and label material.
    samples = {
        spec.id: EVALUATOR._load_sample(
            spec,
            MANIFEST,
        )
        for spec in development_specs
    }

    assert set(samples) == set(DEVELOPMENT_IDS)
    assert not (
        set(samples)
        & set(UNTOUCHED_VALIDATION_IDS)
    )

    baseline_rows = EVALUATOR._run_profile(
        development_specs,
        samples,
        version="2.2.0",
    )

    candidate_rows = EVALUATOR._run_profile(
        development_specs,
        samples,
        version="2.3.0",
    )

    baseline = EVALUATOR._aggregate(
        baseline_rows
    )
    candidate = EVALUATOR._aggregate(
        candidate_rows
    )

    rows = per_sample_rows(
        baseline_rows,
        candidate_rows,
    )

    payload = {
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(timespec="seconds"),
        "audit": (
            "XAUUSD_H1_V2_3_DEVELOPMENT_EVALUATION"
        ),
        "policy": {
            "manifest_metadata_read": True,
            "loaded_sample_material": list(
                DEVELOPMENT_IDS
            ),
            "original_validation_material_loaded": False,
            "historical_locked_test_loaded": False,
            "selection_or_tuning_performed": False,
        },
        "baseline_version": "2.2.0",
        "candidate_version": "2.3.0",
        "baseline": baseline,
        "candidate": candidate,
        "delta": {
            "predicted": (
                candidate["predicted"]
                - baseline["predicted"]
            ),
            "location_true_positives": (
                candidate["location"]["true_positives"]
                - baseline["location"]["true_positives"]
            ),
            "location_false_positives": (
                candidate["location"]["false_positives"]
                - baseline["location"]["false_positives"]
            ),
            "location_false_negatives": (
                candidate["location"]["false_negatives"]
                - baseline["location"]["false_negatives"]
            ),
            "location_precision": delta(
                candidate,
                baseline,
                "location",
                "precision",
            ),
            "location_recall": delta(
                candidate,
                baseline,
                "location",
                "recall",
            ),
            "location_f1": delta(
                candidate,
                baseline,
                "location",
                "f1",
            ),
            "semantic_true_positives": (
                candidate["semantic"]["true_positives"]
                - baseline["semantic"]["true_positives"]
            ),
            "semantic_f1": delta(
                candidate,
                baseline,
                "semantic",
                "f1",
            ),
            "tier_accuracy": delta(
                candidate,
                baseline,
                "semantic",
                "tier_accuracy_on_location_matches",
            ),
            "scope_accuracy": delta(
                candidate,
                baseline,
                "semantic",
                "scope_accuracy_on_location_matches",
            ),
            "major_external_true_positives": (
                candidate["major_external"][
                    "true_positives"
                ]
                - baseline["major_external"][
                    "true_positives"
                ]
            ),
            "major_external_predicted": (
                candidate["major_external"]["predicted"]
                - baseline["major_external"]["predicted"]
            ),
            "major_external_f1": delta(
                candidate,
                baseline,
                "major_external",
                "f1",
            ),
        },
        "per_sample": rows,
    }

    OUTPUT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    OUTPUT.write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )

    print()
    print("V2.3 DEVELOPMENT EVALUATION")
    print("=" * 108)

    for name, result in (
        ("V2.2 BASELINE", baseline),
        ("V2.3 CANDIDATE", candidate),
    ):
        print()
        print(name)
        print("-" * 108)
        print(
            "Location: "
            f"P={result['location']['precision']:.6f} "
            f"R={result['location']['recall']:.6f} "
            f"F1={result['location']['f1']:.6f} "
            f"TP={result['location']['true_positives']} "
            f"FP={result['location']['false_positives']} "
            f"FN={result['location']['false_negatives']}"
        )
        print(
            "Semantic: "
            f"P={result['semantic']['precision']:.6f} "
            f"R={result['semantic']['recall']:.6f} "
            f"F1={result['semantic']['f1']:.6f} "
            f"TP={result['semantic']['true_positives']} "
            f"TierAcc="
            f"{result['semantic']['tier_accuracy_on_location_matches']:.6f} "
            f"ScopeAcc="
            f"{result['semantic']['scope_accuracy_on_location_matches']:.6f}"
        )
        print(
            "Major External: "
            f"P={result['major_external']['precision']:.6f} "
            f"R={result['major_external']['recall']:.6f} "
            f"F1={result['major_external']['f1']:.6f} "
            f"TP={result['major_external']['true_positives']} "
            f"Pred={result['major_external']['predicted']} "
            f"Truth={result['major_external']['ground_truth']}"
        )

    print()
    print("DELTA: V2.3 - V2.2")
    print("-" * 108)
    print(json.dumps(payload["delta"], indent=2))

    print()
    print("PER-SAMPLE DELTAS")
    print("-" * 108)
    print(
        "SAMPLE             dPRED dTP dFP dFN "
        "dLOC_F1  dSEM_F1"
    )

    for row in rows:
        change = row["delta"]
        print(
            f"{row['dataset_id']:<18} "
            f"{change['predicted']:>5} "
            f"{change['true_positives']:>3} "
            f"{change['false_positives']:>3} "
            f"{change['false_negatives']:>3} "
            f"{change['location_f1']:>8.6f} "
            f"{change['semantic_f1']:>8.6f}"
        )

    print()
    print(
        "Original VALIDATION material and historical "
        "locked TEST were not loaded."
    )
    print(f"Report: {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

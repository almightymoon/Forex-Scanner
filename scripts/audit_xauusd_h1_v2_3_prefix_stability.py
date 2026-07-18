#!/usr/bin/env python3
"""Audit v2.3 causal reproducibility on exposed TRAIN samples 001-008."""

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
from swing_engine.models import SwingHierarchyState  # noqa: E402


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
    / "XAUUSD_H1_v2_3_prefix_stability.json"
)

DEVELOPMENT_IDS = tuple(
    f"XAUUSD_H1_{number:03d}"
    for number in range(1, 9)
)

UNTOUCHED_VALIDATION_IDS = tuple(
    f"XAUUSD_H1_{number:03d}"
    for number in range(9, 13)
)


def load_evaluator():
    path = (
        ROOT
        / "scripts"
        / "tune_xauusd_h1_hierarchy.py"
    )

    spec = importlib.util.spec_from_file_location(
        "fxn_v23_prefix_stability_evaluator",
        path,
    )

    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


EVALUATOR = load_evaluator()


def swing_key(swing) -> tuple[int, str]:
    return (
        int(swing.pivot_index),
        swing.direction.value,
    )


def find_match(expected, predictions):
    for candidate in predictions:
        if swing_key(candidate) != swing_key(expected):
            continue

        if abs(
            float(candidate.price)
            - float(expected.price)
        ) > 1e-9:
            continue

        return candidate

    return None


def main() -> int:
    if "2026h1" in str(MANIFEST).lower():
        raise SystemExit(
            "REFUSED: historical locked TEST path supplied"
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
            "REFUSED: selected samples must all be TRAIN"
        )

    if set(DEVELOPMENT_IDS) & set(
        UNTOUCHED_VALIDATION_IDS
    ):
        raise SystemExit(
            "REFUSED: development/validation overlap"
        )

    if any(
        spec.split.upper() == "TEST"
        for spec in specs
    ):
        raise SystemExit(
            "REFUSED: manifest contains TEST material"
        )

    failures: list[dict[str, Any]] = []
    sample_rows: list[dict[str, Any]] = []

    total_swings = 0
    total_first_level_replays = 0
    total_confirmed_major_replays = 0

    for spec in development_specs:
        bars, _ = EVALUATOR._load_sample(
            spec,
            MANIFEST,
        )

        full_predictions, _ = EVALUATOR._detect(
            spec,
            bars,
            version="2.3.0",
        )

        total_swings += len(full_predictions)

        prefix_cache: dict[int, list] = {}

        def predictions_at(
            final_index: int,
        ) -> list:
            if final_index not in prefix_cache:
                prefix_bars = bars[
                    : final_index + 1
                ]

                predictions, _ = EVALUATOR._detect(
                    spec,
                    prefix_bars,
                    version="2.3.0",
                )

                prefix_cache[
                    final_index
                ] = predictions

            return prefix_cache[final_index]

        sample_first_level = 0
        sample_major = 0

        for expected in full_predictions:
            confirmation_index = (
                expected.confirmation_index
            )

            if confirmation_index is None:
                failures.append(
                    {
                        "sample_id": spec.id,
                        "audit": "first_level",
                        "pivot_index": (
                            expected.pivot_index
                        ),
                        "direction": (
                            expected.direction.value
                        ),
                        "reason": (
                            "missing_confirmation_index"
                        ),
                    }
                )
                continue

            confirmation_index = int(
                confirmation_index
            )

            if not (
                0
                <= confirmation_index
                < len(bars)
            ):
                failures.append(
                    {
                        "sample_id": spec.id,
                        "audit": "first_level",
                        "pivot_index": (
                            expected.pivot_index
                        ),
                        "direction": (
                            expected.direction.value
                        ),
                        "reason": (
                            "confirmation_index_out_of_range"
                        ),
                        "confirmation_index": (
                            confirmation_index
                        ),
                    }
                )
                continue

            metadata = expected.metadata or {}

            available_index = metadata.get(
                "available_index"
            )
            structural_index = metadata.get(
                "structural_confirmation_index"
            )

            if (
                available_index is not None
                and confirmation_index
                < int(available_index)
            ):
                failures.append(
                    {
                        "sample_id": spec.id,
                        "audit": "first_level",
                        "pivot_index": (
                            expected.pivot_index
                        ),
                        "direction": (
                            expected.direction.value
                        ),
                        "reason": (
                            "confirmed_before_candidate_available"
                        ),
                        "confirmation_index": (
                            confirmation_index
                        ),
                        "available_index": int(
                            available_index
                        ),
                    }
                )

            if (
                structural_index is not None
                and confirmation_index
                < int(structural_index)
            ):
                failures.append(
                    {
                        "sample_id": spec.id,
                        "audit": "first_level",
                        "pivot_index": (
                            expected.pivot_index
                        ),
                        "direction": (
                            expected.direction.value
                        ),
                        "reason": (
                            "confirmed_before_structure_available"
                        ),
                        "confirmation_index": (
                            confirmation_index
                        ),
                        "structural_confirmation_index": (
                            int(structural_index)
                        ),
                    }
                )

            replay = predictions_at(
                confirmation_index
            )
            match = find_match(
                expected,
                replay,
            )

            total_first_level_replays += 1
            sample_first_level += 1

            if match is None:
                failures.append(
                    {
                        "sample_id": spec.id,
                        "audit": "first_level",
                        "pivot_index": (
                            expected.pivot_index
                        ),
                        "direction": (
                            expected.direction.value
                        ),
                        "reason": (
                            "missing_at_confirmation_prefix"
                        ),
                        "confirmation_index": (
                            confirmation_index
                        ),
                    }
                )
            elif (
                int(match.confirmation_index)
                != confirmation_index
            ):
                failures.append(
                    {
                        "sample_id": spec.id,
                        "audit": "first_level",
                        "pivot_index": (
                            expected.pivot_index
                        ),
                        "direction": (
                            expected.direction.value
                        ),
                        "reason": (
                            "confirmation_index_changed"
                        ),
                        "expected": confirmation_index,
                        "replayed": int(
                            match.confirmation_index
                        ),
                    }
                )

            if (
                expected.hierarchy_state
                is not SwingHierarchyState.CONFIRMED_MAJOR
            ):
                continue

            hierarchy_index = (
                expected.hierarchy_confirmation_index
            )

            if hierarchy_index is None:
                failures.append(
                    {
                        "sample_id": spec.id,
                        "audit": "hierarchy",
                        "pivot_index": (
                            expected.pivot_index
                        ),
                        "direction": (
                            expected.direction.value
                        ),
                        "reason": (
                            "confirmed_major_missing_"
                            "hierarchy_confirmation_index"
                        ),
                    }
                )
                continue

            hierarchy_index = int(
                hierarchy_index
            )

            if not (
                0
                <= hierarchy_index
                < len(bars)
            ):
                failures.append(
                    {
                        "sample_id": spec.id,
                        "audit": "hierarchy",
                        "pivot_index": (
                            expected.pivot_index
                        ),
                        "direction": (
                            expected.direction.value
                        ),
                        "reason": (
                            "hierarchy_index_out_of_range"
                        ),
                        "hierarchy_confirmation_index": (
                            hierarchy_index
                        ),
                    }
                )
                continue

            hierarchy_replay = predictions_at(
                hierarchy_index
            )
            hierarchy_match = find_match(
                expected,
                hierarchy_replay,
            )

            total_confirmed_major_replays += 1
            sample_major += 1

            if hierarchy_match is None:
                failures.append(
                    {
                        "sample_id": spec.id,
                        "audit": "hierarchy",
                        "pivot_index": (
                            expected.pivot_index
                        ),
                        "direction": (
                            expected.direction.value
                        ),
                        "reason": (
                            "missing_at_hierarchy_prefix"
                        ),
                        "hierarchy_confirmation_index": (
                            hierarchy_index
                        ),
                    }
                )
                continue

            if (
                hierarchy_match.hierarchy_state
                is not SwingHierarchyState.CONFIRMED_MAJOR
            ):
                failures.append(
                    {
                        "sample_id": spec.id,
                        "audit": "hierarchy",
                        "pivot_index": (
                            expected.pivot_index
                        ),
                        "direction": (
                            expected.direction.value
                        ),
                        "reason": (
                            "not_confirmed_major_at_"
                            "hierarchy_prefix"
                        ),
                        "replayed_state": (
                            hierarchy_match.hierarchy_state.value
                            if hierarchy_match.hierarchy_state
                            is not None
                            else None
                        ),
                    }
                )

            if (
                hierarchy_match.hierarchy_confirmation_index
                != hierarchy_index
            ):
                failures.append(
                    {
                        "sample_id": spec.id,
                        "audit": "hierarchy",
                        "pivot_index": (
                            expected.pivot_index
                        ),
                        "direction": (
                            expected.direction.value
                        ),
                        "reason": (
                            "hierarchy_confirmation_"
                            "index_changed"
                        ),
                        "expected": hierarchy_index,
                        "replayed": (
                            hierarchy_match
                            .hierarchy_confirmation_index
                        ),
                    }
                )

        sample_rows.append(
            {
                "sample_id": spec.id,
                "predictions": len(
                    full_predictions
                ),
                "first_level_replays": (
                    sample_first_level
                ),
                "confirmed_major_replays": (
                    sample_major
                ),
                "cached_prefixes": len(
                    prefix_cache
                ),
            }
        )

    payload = {
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(timespec="seconds"),
        "audit": (
            "XAUUSD_H1_V2_3_PREFIX_STABILITY"
        ),
        "policy": {
            "loaded_sample_material": list(
                DEVELOPMENT_IDS
            ),
            "original_validation_material_loaded": False,
            "historical_locked_test_loaded": False,
        },
        "summary": {
            "samples": len(
                development_specs
            ),
            "full_predictions": total_swings,
            "first_level_replays": (
                total_first_level_replays
            ),
            "confirmed_major_replays": (
                total_confirmed_major_replays
            ),
            "failures": len(failures),
            "passed": not failures,
        },
        "per_sample": sample_rows,
        "failures": failures,
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
    print("V2.3 PREFIX-STABILITY AUDIT")
    print("=" * 90)
    print(
        "SAMPLE             PREDICTIONS "
        "FIRST_LEVEL CONFIRMED_MAJOR CACHED_PREFIXES"
    )
    print("-" * 90)

    for row in sample_rows:
        print(
            f"{row['sample_id']:<18} "
            f"{row['predictions']:>11} "
            f"{row['first_level_replays']:>11} "
            f"{row['confirmed_major_replays']:>15} "
            f"{row['cached_prefixes']:>15}"
        )

    print()
    print(json.dumps(payload["summary"], indent=2))

    if failures:
        print()
        print("FAILURES")
        print(json.dumps(failures, indent=2))

    print()
    print(
        "Original VALIDATION material and historical "
        "locked TEST were not loaded."
    )
    print(f"Report: {OUTPUT}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

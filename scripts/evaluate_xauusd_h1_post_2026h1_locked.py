#!/usr/bin/env python3
"""Run the one-time post-2026H1 candidate-vs-baseline evaluation.

The evaluator:

- accepts only a frozen human-adjudicated TEST package;
- verifies package, protocol, candidate tag, and repository state;
- writes an irreversible unblinding receipt before detection;
- evaluates v2.3.0 once and v2.2.0 once;
- performs candidate prefix-stability replay;
- applies the promotion gates frozen in the protocol;
- refuses to overwrite any prior evaluation evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from swing_engine.datasets import (  # noqa: E402
    _labels_path,
    load_labels,
    load_manifest,
    load_real_bars,
)
from swing_engine.models import (  # noqa: E402
    SwingHierarchyState,
)


REPORT_NAME = "evaluation_report.json"
UNBLINDING_NAME = "unblinding_receipt.json"
GATE_NAME = "release_gate_receipt.json"

CANDIDATE_TAG = "v2.3.0-rc1"
EVALUATOR_TAG = (
    "xauusd-h1-post-2026h1-evaluator-v1"
)

# Detection/configuration code must remain identical to the frozen candidate.
# datasets.py changed only to support package-relative immutable benchmark files.
ALLOWED_POST_CANDIDATE_ENGINE_CHANGES = {
    "swing_engine/datasets.py",
}

PINNED_DEPENDENCY_SHA256 = {
    "swing_engine/datasets.py": (
        "02505d9cdac675ae221a9a1870e037923558ee57638adbafb7186f283f7a2d50"
    ),
    "scripts/tune_xauusd_h1_hierarchy.py": (
        "321f8cf6cea27d5e1b582e7d129694062cfbe413064f6e1678aa5cd05d819ee4"
    ),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def utc_now() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat(timespec="seconds")


def git_output(*args: str) -> str:
    return subprocess.check_output(
        ["git", *args],
        cwd=ROOT,
        text=True,
    ).strip()


def verify_repository(
    candidate_commit: str,
) -> dict[str, Any]:
    if git_output(
        "status",
        "--porcelain",
    ):
        raise SystemExit(
            "REFUSED: working tree is not clean"
        )

    tag_commit = git_output(
        "rev-list",
        "-n",
        "1",
        CANDIDATE_TAG,
    )

    if tag_commit != candidate_commit:
        raise SystemExit(
            "REFUSED: candidate tag does not resolve "
            "to the frozen candidate commit"
        )

    try:
        evaluator_commit = git_output(
            "rev-parse",
            f"{EVALUATOR_TAG}^{{commit}}",
        )
    except subprocess.CalledProcessError:
        raise SystemExit(
            "REFUSED: evaluator freeze tag is missing"
        ) from None

    evaluator_changes = git_output(
        "diff",
        "--name-only",
        f"{evaluator_commit}..HEAD",
        "--",
        (
            "scripts/"
            "evaluate_xauusd_h1_post_2026h1_locked.py"
        ),
    )

    if evaluator_changes:
        raise SystemExit(
            "REFUSED: locked evaluator changed "
            "after its freeze tag"
        )

    changed_text = git_output(
        "diff",
        "--name-only",
        f"{candidate_commit}..HEAD",
        "--",
        "config/swing_detection.yaml",
        "shared",
        "swing_engine",
    )

    changed = {
        line.strip()
        for line in changed_text.splitlines()
        if line.strip()
    }

    unexpected = (
        changed
        - ALLOWED_POST_CANDIDATE_ENGINE_CHANGES
    )

    if unexpected:
        raise SystemExit(
            "REFUSED: candidate engine inputs changed "
            "after freeze:\n- "
            + "\n- ".join(
                sorted(unexpected)
            )
        )

    dependency_hashes = {}

    for relative, expected in (
        PINNED_DEPENDENCY_SHA256.items()
    ):
        actual = sha256(ROOT / relative)

        if actual != expected:
            raise SystemExit(
                "REFUSED: pinned evaluation "
                f"dependency changed: {relative}\n"
                f"Expected: {expected}\n"
                f"Actual:   {actual}"
            )

        dependency_hashes[relative] = actual

    return {
        "evaluation_head": git_output(
            "rev-parse",
            "HEAD",
        ),
        "candidate_tag": CANDIDATE_TAG,
        "candidate_tag_commit": tag_commit,
        "evaluator_tag": EVALUATOR_TAG,
        "evaluator_tag_commit": (
            evaluator_commit
        ),
        "allowed_post_candidate_changes": (
            sorted(changed)
        ),
        "dependency_sha256": (
            dependency_hashes
        ),
    }


def load_helpers():
    path = (
        ROOT
        / "scripts"
        / "tune_xauusd_h1_hierarchy.py"
    )

    spec = importlib.util.spec_from_file_location(
        "fxn_post_2026h1_locked_evaluation_helpers",
        path,
    )

    if spec is None or spec.loader is None:
        raise RuntimeError(
            f"Unable to load {path}"
        )

    module = importlib.util.module_from_spec(
        spec
    )
    spec.loader.exec_module(module)
    return module


HELPERS = load_helpers()


def load_package(
    package_root: Path,
) -> dict[str, Any]:
    manifest_path = (
        package_root
        / (
            "XAUUSD_H1_post_2026H1_locked."
            "human.manifest.json"
        )
    )

    labels_path = (
        package_root
        / (
            "XAUUSD_H1_post_2026H1_locked."
            "human.json"
        )
    )

    data_path = (
        package_root
        / (
            "XAUUSD_H1_post_2026H1_locked."
            "real.csv.gz"
        )
    )

    receipt_path = (
        package_root
        / "freeze_receipt.json"
    )

    for path in (
        manifest_path,
        labels_path,
        data_path,
        receipt_path,
    ):
        if not path.exists():
            raise SystemExit(
                "REFUSED: missing frozen package "
                f"file {path}"
            )

    manifest = json.loads(
        manifest_path.read_text(
            encoding="utf-8"
        )
    )

    labels = json.loads(
        labels_path.read_text(
            encoding="utf-8"
        )
    )

    receipt = json.loads(
        receipt_path.read_text(
            encoding="utf-8"
        )
    )

    if manifest.get("status") != (
        "FROZEN_UNBLINDED_LABELS_"
        "NOT_EVALUATED"
    ):
        raise SystemExit(
            "REFUSED: package manifest is not "
            "evaluation-ready"
        )

    if labels.get("status") != (
        "FROZEN_HUMAN_ADJUDICATED"
    ):
        raise SystemExit(
            "REFUSED: labels are not frozen "
            "human adjudication"
        )

    if labels.get("label_origin") != (
        "HUMAN_ADJUDICATED"
    ):
        raise SystemExit(
            "REFUSED: label origin is not "
            "HUMAN_ADJUDICATED"
        )

    if receipt.get("status") != (
        "FROZEN_HUMAN_ADJUDICATED_"
        "NOT_EVALUATED"
    ):
        raise SystemExit(
            "REFUSED: freeze receipt is not "
            "evaluation-ready"
        )

    expected = receipt["outputs"]

    actual = {
        "data_sha256": sha256(data_path),
        "labels_sha256": sha256(
            labels_path
        ),
        "manifest_sha256": sha256(
            manifest_path
        ),
    }

    if actual != expected:
        raise SystemExit(
            "REFUSED: frozen package checksum "
            "mismatch\n"
            f"Expected: {expected}\n"
            f"Actual:   {actual}"
        )

    controls = manifest.get(
        "contamination_controls",
        {},
    )

    for key in (
        "predictions_loaded",
        "swing_detector_executed",
        "candidate_evaluated",
        "baseline_evaluated",
    ):
        if controls.get(key) is not False:
            raise SystemExit(
                "REFUSED: package contamination "
                f"control {key} failed"
            )

    protocol_path = Path(
        receipt[
            "source_evidence"
        ]["protocol"]["path"]
    )

    if not protocol_path.is_absolute():
        protocol_path = (
            ROOT / protocol_path
        ).resolve()

    if not protocol_path.exists():
        raise SystemExit(
            "REFUSED: frozen protocol is missing"
        )

    expected_protocol_sha = (
        receipt[
            "source_evidence"
        ]["protocol"]["sha256"]
    )

    if sha256(
        protocol_path
    ) != expected_protocol_sha:
        raise SystemExit(
            "REFUSED: frozen protocol checksum "
            "mismatch"
        )

    protocol = json.loads(
        protocol_path.read_text(
            encoding="utf-8"
        )
    )

    if protocol.get("protocol_id") != (
        manifest.get("protocol_id")
    ):
        raise SystemExit(
            "REFUSED: protocol ID mismatch"
        )

    candidate = protocol["candidate"]
    baseline = protocol["baseline"]

    if receipt.get("candidate") != candidate:
        raise SystemExit(
            "REFUSED: candidate metadata mismatch"
        )

    if receipt.get("baseline") != baseline:
        raise SystemExit(
            "REFUSED: baseline metadata mismatch"
        )

    specs = load_manifest(
        manifest_path
    )

    expected_windows = int(
        protocol[
            "window_selection"
        ]["bucket_count"]
    )

    if len(specs) != expected_windows:
        raise SystemExit(
            "REFUSED: expected "
            f"{expected_windows} TEST windows, "
            f"found {len(specs)}"
        )

    if any(
        spec.split.upper() != "TEST"
        for spec in specs
    ):
        raise SystemExit(
            "REFUSED: frozen manifest contains "
            "a non-TEST sample"
        )

    return {
        "manifest_path": manifest_path,
        "labels_path": labels_path,
        "data_path": data_path,
        "receipt_path": receipt_path,
        "manifest": manifest,
        "labels": labels,
        "receipt": receipt,
        "protocol": protocol,
        "protocol_path": protocol_path,
        "specs": specs,
        "hashes": actual,
    }


def load_samples(
    specs: list,
    manifest_path: Path,
) -> dict[str, tuple[list, list]]:
    samples = {}

    for spec in specs:
        bars = load_real_bars(
            spec,
            manifest_path=manifest_path,
        )

        labels_path = _labels_path(
            spec,
            manifest_path=manifest_path,
        )

        labels, _ = load_labels(
            labels_path,
            sample_id=spec.sample_id,
        )

        if (
            spec.labelable_start_index
            is not None
        ):
            labels = [
                label
                for label in labels
                if label.pivot_index
                >= spec.labelable_start_index
            ]

        if (
            spec.labelable_end_index
            is not None
        ):
            labels = [
                label
                for label in labels
                if label.pivot_index
                <= spec.labelable_end_index
            ]

        samples[spec.id] = (
            bars,
            labels,
        )

    return samples


def run_profile(
    specs: list,
    samples: dict[
        str,
        tuple[list, list],
    ],
    *,
    version: str,
    benchmark_id: str,
) -> tuple[
    list[dict[str, Any]],
    dict[str, Any],
]:
    rows = []

    for spec in specs:
        bars, labels = samples[spec.id]

        predictions, config = (
            HELPERS._detect(
                spec,
                bars,
                version=version,
            )
        )

        row = HELPERS._evaluate_sample(
            spec,
            bars,
            labels,
            predictions,
            config,
            version=version,
        )

        # Replace the helper's development-only
        # benchmark metadata.
        row["benchmark_version"] = (
            benchmark_id
        )

        rows.append(row)

    return (
        rows,
        HELPERS._aggregate(rows),
    )


def swing_key(
    swing,
) -> tuple[int, str]:
    return (
        int(swing.pivot_index),
        swing.direction.value,
    )


def find_match(
    expected,
    predictions,
):
    for candidate in predictions:
        if swing_key(candidate) != (
            swing_key(expected)
        ):
            continue

        if abs(
            float(candidate.price)
            - float(expected.price)
        ) > 1e-9:
            continue

        return candidate

    return None


def prefix_audit(
    specs: list,
    samples: dict[
        str,
        tuple[list, list],
    ],
    *,
    version: str,
) -> dict[str, Any]:
    failures: list[
        dict[str, Any]
    ] = []

    per_sample = []
    total_predictions = 0
    first_level_replays = 0
    confirmed_major_replays = 0

    for spec in specs:
        bars, _ = samples[spec.id]

        full, _ = HELPERS._detect(
            spec,
            bars,
            version=version,
        )

        total_predictions += len(full)

        cache: dict[int, list] = {}

        def predictions_at(
            index: int,
        ) -> list:
            if index not in cache:
                prefix = bars[
                    : index + 1
                ]

                detected, _ = (
                    HELPERS._detect(
                        spec,
                        prefix,
                        version=version,
                    )
                )

                cache[index] = detected

            return cache[index]

        sample_first = 0
        sample_major = 0

        for expected in full:
            confirmation = (
                expected.confirmation_index
            )

            if confirmation is None:
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

            confirmation = int(
                confirmation
            )

            if not (
                0 <= confirmation < len(bars)
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
                            "confirmation_index_"
                            "out_of_range"
                        ),
                        "confirmation_index": (
                            confirmation
                        ),
                    }
                )
                continue

            metadata = (
                expected.metadata or {}
            )

            available = metadata.get(
                "available_index"
            )

            structural = metadata.get(
                "structural_confirmation_index"
            )

            if (
                available is not None
                and confirmation
                < int(available)
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
                            "confirmed_before_"
                            "candidate_available"
                        ),
                    }
                )

            if (
                structural is not None
                and confirmation
                < int(structural)
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
                            "confirmed_before_"
                            "structure_available"
                        ),
                    }
                )

            replay = predictions_at(
                confirmation
            )

            match = find_match(
                expected,
                replay,
            )

            first_level_replays += 1
            sample_first += 1

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
                            "missing_at_"
                            "confirmation_prefix"
                        ),
                        "confirmation_index": (
                            confirmation
                        ),
                    }
                )

            elif int(
                match.confirmation_index
            ) != confirmation:
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
                        "expected": confirmation,
                        "replayed": int(
                            match.confirmation_index
                        ),
                    }
                )

            if (
                expected.hierarchy_state
                is not
                SwingHierarchyState.CONFIRMED_MAJOR
            ):
                continue

            hierarchy_index = (
                expected
                .hierarchy_confirmation_index
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
                    }
                )
                continue

            replay = predictions_at(
                hierarchy_index
            )

            match = find_match(
                expected,
                replay,
            )

            confirmed_major_replays += 1
            sample_major += 1

            if match is None:
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
                            "missing_at_"
                            "hierarchy_prefix"
                        ),
                    }
                )
                continue

            if (
                match.hierarchy_state
                is not
                SwingHierarchyState.CONFIRMED_MAJOR
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
                    }
                )

            if (
                match
                .hierarchy_confirmation_index
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
                    }
                )

        per_sample.append(
            {
                "sample_id": spec.id,
                "predictions": len(full),
                "first_level_replays": (
                    sample_first
                ),
                "confirmed_major_replays": (
                    sample_major
                ),
                "cached_prefixes": len(
                    cache
                ),
            }
        )

    return {
        "summary": {
            "samples": len(specs),
            "full_predictions": (
                total_predictions
            ),
            "first_level_replays": (
                first_level_replays
            ),
            "confirmed_major_replays": (
                confirmed_major_replays
            ),
            "failures": len(failures),
            "passed": not failures,
        },
        "per_sample": per_sample,
        "failures": failures,
    }


def gate_receipt(
    *,
    protocol: dict[str, Any],
    candidate: dict[str, Any],
    baseline: dict[str, Any],
    candidate_rows: list[
        dict[str, Any]
    ],
    prefix: dict[str, Any],
) -> dict[str, Any]:
    gates = protocol[
        "promotion_gates"
    ]

    worst_window = min(
        float(row["f1_score"])
        for row in candidate_rows
    )

    location_delta = round(
        float(
            candidate["location"]["f1"]
        )
        - float(
            baseline["location"]["f1"]
        ),
        6,
    )

    semantic_delta = round(
        float(
            candidate["semantic"]["f1"]
        )
        - float(
            baseline["semantic"]["f1"]
        ),
        6,
    )

    values = {
        "prefix_stability_failures_max": (
            prefix["summary"]["failures"]
        ),
        "location_precision_min": (
            candidate[
                "location"
            ]["precision"]
        ),
        "location_recall_min": (
            candidate[
                "location"
            ]["recall"]
        ),
        "location_f1_min": (
            candidate["location"]["f1"]
        ),
        "semantic_f1_min": (
            candidate["semantic"]["f1"]
        ),
        "major_external_precision_min": (
            candidate[
                "major_external"
            ]["precision"]
        ),
        "major_external_recall_min": (
            candidate[
                "major_external"
            ]["recall"]
        ),
        "worst_window_location_f1_min": (
            worst_window
        ),
        (
            "candidate_location_f1_"
            "delta_vs_v2_2_min"
        ): location_delta,
        (
            "candidate_semantic_f1_"
            "delta_vs_v2_2_min"
        ): semantic_delta,
    }

    checks = []

    for name, threshold in (
        gates.items()
    ):
        actual = values[name]
        maximum_gate = name.endswith(
            "_max"
        )

        passed = (
            actual <= threshold
            if maximum_gate
            else actual >= threshold
        )

        checks.append(
            {
                "gate": name,
                "operator": (
                    "<="
                    if maximum_gate
                    else ">="
                ),
                "threshold": threshold,
                "actual": actual,
                "passed": passed,
            }
        )

    all_passed = all(
        check["passed"]
        for check in checks
    )

    return {
        "status": (
            "PASS"
            if all_passed
            else "FAIL"
        ),
        "decision": (
            "PROMOTE_V2_3_0_FINAL"
            if all_passed
            else "REMAIN_V2_3_0_RC1"
        ),
        "all_gates_passed": (
            all_passed
        ),
        "checks": checks,
        "derived": {
            "worst_window_location_f1": (
                worst_window
            ),
            (
                "candidate_location_f1_"
                "delta_vs_v2_2"
            ): location_delta,
            (
                "candidate_semantic_f1_"
                "delta_vs_v2_2"
            ): semantic_delta,
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__
    )

    parser.add_argument(
        "--package-root",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--output-root",
        type=Path,
        required=True,
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    package_root = (
        args.package_root.resolve()
    )

    output_root = (
        args.output_root.resolve()
    )

    if output_root.exists():
        raise SystemExit(
            "REFUSED: one-time evaluation "
            f"output already exists: {output_root}"
        )

    if (
        output_root == package_root
        or package_root in output_root.parents
    ):
        raise SystemExit(
            "REFUSED: evaluation output root must "
            "be outside the immutable frozen package"
        )

    package = load_package(
        package_root
    )

    protocol = package["protocol"]

    candidate_commit = protocol[
        "candidate"
    ]["commit"]

    repository = verify_repository(
        candidate_commit
    )

    candidate_label = protocol[
        "candidate"
    ]["version"]

    candidate_version = (
        candidate_label.split("-")[0]
    )

    baseline_version = protocol[
        "baseline"
    ]["version"]

    report_path = (
        output_root / REPORT_NAME
    )

    unblinding_path = (
        output_root / UNBLINDING_NAME
    )

    gate_path = (
        output_root / GATE_NAME
    )

    samples = load_samples(
        package["specs"],
        package["manifest_path"],
    )

    output_root.mkdir(
        parents=True
    )

    started_at = utc_now()

    unblinding = {
        "dataset_id": package[
            "manifest"
        ]["dataset_id"],
        "protocol_id": protocol[
            "protocol_id"
        ],
        "state": "UNBLINDING_STARTED",
        "started_at_utc": started_at,
        "candidate_label": (
            candidate_label
        ),
        "candidate_engine_version": (
            candidate_version
        ),
        "candidate_commit": (
            candidate_commit
        ),
        "baseline_version": (
            baseline_version
        ),
        "package_hashes": package[
            "hashes"
        ],
        "repository": repository,
        "policy": {
            "candidate_evaluations_allowed": 1,
            "baseline_evaluations_allowed": 1,
            "parameter_selection": "NONE",
            "error_analysis_before_decision": False,
            "tuning_after_unblinding": False,
        },
    }

    # Irreversible marker written immediately
    # before the first prediction is generated.
    unblinding_path.write_text(
        json.dumps(
            unblinding,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    candidate_rows, candidate = (
        run_profile(
            package["specs"],
            samples,
            version=candidate_version,
            benchmark_id=package[
                "manifest"
            ]["dataset_id"],
        )
    )

    baseline_rows, baseline = (
        run_profile(
            package["specs"],
            samples,
            version=baseline_version,
            benchmark_id=package[
                "manifest"
            ]["dataset_id"],
        )
    )

    prefix = prefix_audit(
        package["specs"],
        samples,
        version=candidate_version,
    )

    gate = gate_receipt(
        protocol=protocol,
        candidate=candidate,
        baseline=baseline,
        candidate_rows=candidate_rows,
        prefix=prefix,
    )

    completed_at = utc_now()

    report = {
        "dataset_id": package[
            "manifest"
        ]["dataset_id"],
        "protocol_id": protocol[
            "protocol_id"
        ],
        "benchmark_status": package[
            "manifest"
        ]["status"],
        "started_at_utc": started_at,
        "completed_at_utc": (
            completed_at
        ),
        "evaluation_policy": {
            "split": "TEST",
            "run_policy": (
                "ONE_TIME_CANDIDATE_AND_"
                "BASELINE"
            ),
            "parameter_selection": "NONE",
            "error_analysis_before_decision": (
                False
            ),
            "tuning_after_unblinding": (
                False
            ),
        },
        "candidate": {
            "label": candidate_label,
            "engine_version": (
                candidate_version
            ),
            "commit": candidate_commit,
            "aggregate": candidate,
            "per_sample": (
                candidate_rows
            ),
            "prefix_stability": prefix,
        },
        "baseline": {
            "engine_version": (
                baseline_version
            ),
            "aggregate": baseline,
            "per_sample": baseline_rows,
        },
        "release_gate": gate,
    }

    report_path.write_text(
        json.dumps(
            report,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    unblinding.update(
        {
            "state": "COMPLETED",
            "completed_at_utc": (
                completed_at
            ),
            "report": REPORT_NAME,
            "report_sha256": sha256(
                report_path
            ),
        }
    )

    unblinding_path.write_text(
        json.dumps(
            unblinding,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    gate_document = {
        "dataset_id": report[
            "dataset_id"
        ],
        "protocol_id": report[
            "protocol_id"
        ],
        "generated_at_utc": (
            completed_at
        ),
        "candidate": {
            "label": candidate_label,
            "engine_version": (
                candidate_version
            ),
            "commit": candidate_commit,
        },
        "baseline": {
            "engine_version": (
                baseline_version
            ),
        },
        **gate,
        "evidence": {
            "evaluation_report": {
                "path": REPORT_NAME,
                "sha256": sha256(
                    report_path
                ),
            },
            "unblinding_receipt": {
                "path": UNBLINDING_NAME,
                "sha256": sha256(
                    unblinding_path
                ),
            },
            "frozen_package": (
                package["hashes"]
            ),
        },
    }

    gate_path.write_text(
        json.dumps(
            gate_document,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print()
    print(
        "ONE-TIME POST-2026H1 "
        "LOCKED EVALUATION COMPLETE"
    )
    print("=" * 76)
    print(
        "Decision:",
        gate["decision"],
    )
    print(
        "All gates passed:",
        gate["all_gates_passed"],
    )
    print(
        "Candidate location:",
        candidate["location"],
    )
    print(
        "Candidate semantic:",
        candidate["semantic"],
    )
    print(
        "Candidate Major External:",
        candidate[
            "major_external"
        ],
    )
    print(
        "Baseline location:",
        baseline["location"],
    )
    print(
        "Baseline semantic:",
        baseline["semantic"],
    )
    print(
        "Prefix failures:",
        prefix["summary"]["failures"],
    )
    print("Report:", report_path)
    print(
        "Unblinding receipt:",
        unblinding_path,
    )
    print(
        "Release-gate receipt:",
        gate_path,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

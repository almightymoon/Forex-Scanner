#!/usr/bin/env python3
"""One-time retrospective engineering-gate evaluation.

Accepts only a completed frozen HUMAN_ADJUDICATED TEST package for the
2022–2024 retrospective holdout.

Decision values:
  PASS_RETROSPECTIVE_ENGINEERING_GATE
  FAIL_RETROSPECTIVE_ENGINEERING_GATE

Never emits PROMOTE_V2_3_0_FINAL. Final production certification still
requires the prospective post-2026H1 benchmark.

This script must not be run against the real retrospective package during
construction of the source/protocol/window artifacts.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def load_post_evaluator():
    path = (
        ROOT
        / "scripts"
        / "evaluate_xauusd_h1_post_2026h1_locked.py"
    )
    spec = importlib.util.spec_from_file_location(
        "fxn_post_2026h1_evaluator_for_retrospective",
        path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


POST = load_post_evaluator()

REPORT_NAME = "evaluation_report.json"
UNBLINDING_NAME = "unblinding_receipt.json"
GATE_NAME = "retrospective_gate_receipt.json"

DATA_FILENAME = (
    "XAUUSD_H1_2022_2024_retrospective_locked.real.csv.gz"
)
LABELS_FILENAME = (
    "XAUUSD_H1_2022_2024_retrospective_locked.human.json"
)
MANIFEST_FILENAME = (
    "XAUUSD_H1_2022_2024_retrospective_locked."
    "human.manifest.json"
)

PASS_DECISION = "PASS_RETROSPECTIVE_ENGINEERING_GATE"
FAIL_DECISION = "FAIL_RETROSPECTIVE_ENGINEERING_GATE"
FORBIDDEN_DECISION = "PROMOTE_V2_3_0_FINAL"

CERTIFICATION_WARNING = (
    "Passing this retrospective engineering gate does not replace the "
    "frozen prospective post-2026H1 final certification."
)

RETROSPECTIVE_EVALUATOR_TAG = (
    "xauusd-h1-2022-2024-retrospective-evaluator-v1"
)
RETROSPECTIVE_EVALUATOR_SCRIPT = (
    "scripts/evaluate_xauusd_h1_2022_2024_retrospective_locked.py"
)

# Re-export helpers used by tests.
sha256 = POST.sha256
utc_now = POST.utc_now
load_samples = POST.load_samples
run_profile = POST.run_profile
prefix_audit = POST.prefix_audit
CANDIDATE_TAG = POST.CANDIDATE_TAG


def verify_repository(candidate_commit: str) -> dict[str, Any]:
    """Seal candidate, post evaluator, and this retrospective wrapper.

    POST.verify_repository already seals v2.3.0-rc1, the post-2026H1 evaluator
    tag, and pinned evaluation dependencies. This wrapper additionally freezes
    the retrospective evaluator script under RETROSPECTIVE_EVALUATOR_TAG.
    """
    evidence = dict(POST.verify_repository(candidate_commit))

    try:
        retrospective_commit = POST.git_output(
            "rev-parse",
            f"{RETROSPECTIVE_EVALUATOR_TAG}^{{commit}}",
        )
    except subprocess.CalledProcessError:
        raise SystemExit(
            "REFUSED: retrospective evaluator freeze tag is missing"
        ) from None

    retrospective_changes = POST.git_output(
        "diff",
        "--name-only",
        f"{retrospective_commit}..HEAD",
        "--",
        RETROSPECTIVE_EVALUATOR_SCRIPT,
    )

    if retrospective_changes.strip():
        raise SystemExit(
            "REFUSED: retrospective evaluator changed after its freeze tag"
        )

    evidence["retrospective_evaluator_tag"] = (
        RETROSPECTIVE_EVALUATOR_TAG
    )
    evidence["retrospective_evaluator_tag_commit"] = (
        retrospective_commit
    )
    return evidence


def gate_receipt(
    *,
    protocol: dict[str, Any],
    candidate: dict[str, Any],
    baseline: dict[str, Any],
    candidate_rows: list[dict[str, Any]],
    prefix: dict[str, Any],
) -> dict[str, Any]:
    adapted = dict(protocol)
    if "engineering_gates" in adapted:
        adapted["promotion_gates"] = adapted["engineering_gates"]
    if "promotion_gates" not in adapted:
        raise SystemExit(
            "REFUSED: protocol missing engineering_gates/promotion_gates"
        )

    result = POST.gate_receipt(
        protocol=adapted,
        candidate=candidate,
        baseline=baseline,
        candidate_rows=candidate_rows,
        prefix=prefix,
    )

    decision = (
        PASS_DECISION
        if result["all_gates_passed"]
        else FAIL_DECISION
    )
    if decision == FORBIDDEN_DECISION:
        raise SystemExit(
            "REFUSED: retrospective evaluator attempted forbidden decision"
        )

    result["decision"] = decision
    result["benchmark_type"] = "RETROSPECTIVE_HOLDOUT"
    result["certification_warning"] = CERTIFICATION_WARNING
    result["forbidden_decision_values"] = [FORBIDDEN_DECISION]
    return result


def load_package(package_root: Path) -> dict[str, Any]:
    package_root = package_root.resolve()

    manifest_path = package_root / MANIFEST_FILENAME
    labels_path = package_root / LABELS_FILENAME
    data_path = package_root / DATA_FILENAME
    receipt_path = package_root / "freeze_receipt.json"

    for path in (
        manifest_path,
        labels_path,
        data_path,
        receipt_path,
    ):
        if not path.exists():
            raise SystemExit(
                f"REFUSED: missing frozen package file {path}"
            )

    manifest = json.loads(
        manifest_path.read_text(encoding="utf-8")
    )
    labels = json.loads(
        labels_path.read_text(encoding="utf-8")
    )
    receipt = json.loads(
        receipt_path.read_text(encoding="utf-8")
    )

    if manifest.get("status") != (
        "FROZEN_UNBLINDED_LABELS_NOT_EVALUATED"
    ):
        raise SystemExit(
            "REFUSED: package manifest is not evaluation-ready"
        )

    if labels.get("status") != "FROZEN_HUMAN_ADJUDICATED":
        raise SystemExit(
            "REFUSED: labels are not frozen human adjudication"
        )

    if labels.get("label_origin") != "HUMAN_ADJUDICATED":
        raise SystemExit(
            "REFUSED: label origin is not HUMAN_ADJUDICATED"
        )

    if receipt.get("status") != (
        "FROZEN_HUMAN_ADJUDICATED_NOT_EVALUATED"
    ):
        raise SystemExit(
            "REFUSED: freeze receipt is not evaluation-ready"
        )

    expected = receipt["outputs"]
    actual = {
        "data_sha256": sha256(data_path),
        "labels_sha256": sha256(labels_path),
        "manifest_sha256": sha256(manifest_path),
    }
    if actual != expected:
        raise SystemExit(
            "REFUSED: frozen package checksum mismatch\n"
            f"Expected: {expected}\n"
            f"Actual:   {actual}"
        )

    controls = manifest.get("contamination_controls", {})
    for key in (
        "predictions_loaded",
        "swing_detector_executed",
        "candidate_evaluated",
        "baseline_evaluated",
    ):
        if controls.get(key) is not False:
            raise SystemExit(
                f"REFUSED: package contamination control {key} failed"
            )

    protocol_path = Path(
        receipt["source_evidence"]["protocol"]["path"]
    )
    if not protocol_path.is_absolute():
        protocol_path = (ROOT / protocol_path).resolve()

    if not protocol_path.exists():
        raise SystemExit("REFUSED: frozen protocol is missing")

    expected_protocol_sha = receipt["source_evidence"]["protocol"][
        "sha256"
    ]
    if sha256(protocol_path) != expected_protocol_sha:
        raise SystemExit(
            "REFUSED: frozen protocol checksum mismatch"
        )

    protocol = json.loads(
        protocol_path.read_text(encoding="utf-8")
    )

    if protocol.get("protocol_id") != manifest.get("protocol_id"):
        raise SystemExit("REFUSED: protocol ID mismatch")

    if protocol.get("benchmark_type") != "RETROSPECTIVE_HOLDOUT":
        raise SystemExit(
            "REFUSED: protocol is not RETROSPECTIVE_HOLDOUT"
        )

    if protocol.get("protocol_id") != (
        "XAUUSD_H1_2022_2024_RETROSPECTIVE_LOCKED_V1"
    ):
        raise SystemExit("REFUSED: unexpected retrospective protocol_id")

    if FORBIDDEN_DECISION in protocol.get("decision_values", []):
        raise SystemExit(
            "REFUSED: protocol lists forbidden promotion decision"
        )

    candidate = protocol["candidate"]
    baseline = protocol["baseline"]

    if receipt.get("candidate") != candidate:
        raise SystemExit("REFUSED: candidate metadata mismatch")
    if receipt.get("baseline") != baseline:
        raise SystemExit("REFUSED: baseline metadata mismatch")

    from swing_engine.datasets import load_manifest

    specs = load_manifest(manifest_path)

    expected_windows = int(
        protocol["window_selection"]["bucket_count"]
    )
    if len(specs) != expected_windows:
        raise SystemExit(
            f"REFUSED: expected {expected_windows} TEST windows, "
            f"found {len(specs)}"
        )

    if any(spec.split.upper() != "TEST" for spec in specs):
        raise SystemExit(
            "REFUSED: frozen manifest contains a non-TEST sample"
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    package_root = args.package_root.resolve()
    output_root = args.output_root.resolve()

    if output_root.exists():
        raise SystemExit(
            "REFUSED: one-time evaluation output already exists: "
            f"{output_root}"
        )

    if (
        output_root == package_root
        or package_root in output_root.parents
    ):
        raise SystemExit(
            "REFUSED: evaluation output root must be outside the "
            "immutable frozen package"
        )

    package = load_package(package_root)
    protocol = package["protocol"]
    candidate_commit = protocol["candidate"]["commit"]
    repository = verify_repository(candidate_commit)

    candidate_label = protocol["candidate"]["version"]
    candidate_version = candidate_label.split("-")[0]
    baseline_version = protocol["baseline"]["version"]

    report_path = output_root / REPORT_NAME
    unblinding_path = output_root / UNBLINDING_NAME
    gate_path = output_root / GATE_NAME

    samples = load_samples(
        package["specs"],
        package["manifest_path"],
    )

    output_root.mkdir(parents=True)
    started_at = utc_now()

    unblinding = {
        "dataset_id": package["manifest"]["dataset_id"],
        "protocol_id": protocol["protocol_id"],
        "benchmark_type": "RETROSPECTIVE_HOLDOUT",
        "state": "UNBLINDING_STARTED",
        "started_at_utc": started_at,
        "candidate_label": candidate_label,
        "candidate_engine_version": candidate_version,
        "candidate_commit": candidate_commit,
        "baseline_version": baseline_version,
        "package_hashes": package["hashes"],
        "repository": repository,
        "policy": {
            "candidate_evaluations_allowed": 1,
            "baseline_evaluations_allowed": 1,
            "parameter_selection": "NONE",
            "error_analysis_before_decision": False,
            "tuning_after_unblinding": False,
        },
        "certification_warning": CERTIFICATION_WARNING,
    }

    unblinding_path.write_text(
        json.dumps(unblinding, indent=2) + "\n",
        encoding="utf-8",
    )

    candidate_rows, candidate = run_profile(
        package["specs"],
        samples,
        version=candidate_version,
        benchmark_id=package["manifest"]["dataset_id"],
    )

    baseline_rows, baseline = run_profile(
        package["specs"],
        samples,
        version=baseline_version,
        benchmark_id=package["manifest"]["dataset_id"],
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

    if gate["decision"] == FORBIDDEN_DECISION:
        raise SystemExit(
            "REFUSED: retrospective decision must never promote final"
        )

    completed_at = utc_now()

    report = {
        "dataset_id": package["manifest"]["dataset_id"],
        "protocol_id": protocol["protocol_id"],
        "benchmark_type": "RETROSPECTIVE_HOLDOUT",
        "benchmark_status": package["manifest"]["status"],
        "started_at_utc": started_at,
        "completed_at_utc": completed_at,
        "certification_warning": CERTIFICATION_WARNING,
        "evaluation_policy": {
            "split": "TEST",
            "run_policy": "ONE_TIME_CANDIDATE_AND_BASELINE",
            "parameter_selection": "NONE",
            "error_analysis_before_decision": False,
            "tuning_after_unblinding": False,
        },
        "candidate": {
            "label": candidate_label,
            "engine_version": candidate_version,
            "commit": candidate_commit,
            "aggregate": candidate,
            "per_sample": candidate_rows,
            "prefix_stability": prefix,
        },
        "baseline": {
            "engine_version": baseline_version,
            "aggregate": baseline,
            "per_sample": baseline_rows,
        },
        "retrospective_gate": gate,
    }

    report_path.write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )

    unblinding.update(
        {
            "state": "COMPLETED",
            "completed_at_utc": completed_at,
            "report": REPORT_NAME,
            "report_sha256": sha256(report_path),
        }
    )
    unblinding_path.write_text(
        json.dumps(unblinding, indent=2) + "\n",
        encoding="utf-8",
    )

    gate_document = {
        "dataset_id": report["dataset_id"],
        "protocol_id": report["protocol_id"],
        "benchmark_type": "RETROSPECTIVE_HOLDOUT",
        "generated_at_utc": completed_at,
        "candidate": {
            "label": candidate_label,
            "engine_version": candidate_version,
            "commit": candidate_commit,
        },
        "baseline": {
            "engine_version": baseline_version,
        },
        **gate,
        "evidence": {
            "evaluation_report": {
                "path": REPORT_NAME,
                "sha256": sha256(report_path),
            },
            "unblinding_receipt": {
                "path": UNBLINDING_NAME,
                "sha256": sha256(unblinding_path),
            },
            "frozen_package": package["hashes"],
        },
    }

    gate_path.write_text(
        json.dumps(gate_document, indent=2) + "\n",
        encoding="utf-8",
    )

    print()
    print("ONE-TIME RETROSPECTIVE ENGINEERING-GATE EVALUATION COMPLETE")
    print("=" * 76)
    print("Decision:", gate["decision"])
    print("Warning:", CERTIFICATION_WARNING)
    print("Report:", report_path)
    print("Unblinding receipt:", unblinding_path)
    print("Retrospective-gate receipt:", gate_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

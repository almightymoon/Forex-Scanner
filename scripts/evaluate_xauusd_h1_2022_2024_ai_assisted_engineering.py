#!/usr/bin/env python3
"""One-time AI-assisted engineering diagnostic evaluation.

Accepts only a frozen AI_ASSISTED_ENGINEERING_DIAGNOSTIC package.

Allowed diagnostic conclusions:
  CANDIDATE_OUTPERFORMS_BASELINE_ON_AI_DRAFT
  BASELINE_OUTPERFORMS_CANDIDATE_ON_AI_DRAFT
  MIXED_AI_DRAFT_RESULT
  AI_DRAFT_DIAGNOSTIC_INCONCLUSIVE

Forbidden values (never emitted):
  PROMOTE_V2_3_0_FINAL
  PASS_RETROSPECTIVE_ENGINEERING_GATE
  FAIL_RETROSPECTIVE_ENGINEERING_GATE
  PRODUCTION_READY
  RELEASE_APPROVED

This script must not be run against the real AI package until the evaluator
script is committed and tagged as xauusd-h1-2022-2024-ai-draft-evaluator-v1.
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
    path = ROOT / "scripts" / "evaluate_xauusd_h1_post_2026h1_locked.py"
    spec = importlib.util.spec_from_file_location(
        "fxn_post_2026h1_evaluator_for_ai_draft",
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
DIAGNOSTIC_NAME = "ai_draft_diagnostic_receipt.json"

DATA_FILENAME = "XAUUSD_H1_2022_2024_ai_draft.real.csv.gz"
LABELS_FILENAME = "XAUUSD_H1_2022_2024_ai_draft.labels.json"
MANIFEST_FILENAME = "XAUUSD_H1_2022_2024_ai_draft.manifest.json"

BENCHMARK_TYPE = "AI_ASSISTED_ENGINEERING_DIAGNOSTIC"
LABEL_ORIGIN = "AI_ASSISTED_ENGINEERING_DRAFT"
PACKAGE_STATUS = "FROZEN_AI_ASSISTED_ENGINEERING_DRAFT_NOT_EVALUATED"
PROTOCOL_ID = "XAUUSD_H1_2022_2024_RETROSPECTIVE_LOCKED_V1"

# Local AI-diagnostic constants (do not alter global annotation policy).
AI_DRAFT_ORIGIN = LABEL_ORIGIN
AI_DIAGNOSTIC_TYPE = BENCHMARK_TYPE
AI_DRAFT_STATUS = PACKAGE_STATUS

REFUSED_LABEL_ORIGINS = frozenset(
    {
        "HUMAN",
        "HUMAN_DRAFT",
        "HUMAN_ADJUDICATED",
        "AI_ASSISTED_EXPERT_DRAFT",
    }
)

EXPECTED_PACKAGE_OUTPUTS = {
    "data_sha256": (
        "b3db9b67e7c24b028805df660e13bbc2cdb83d3ac4b0e2024f2e622ec81d8b68"
    ),
    "labels_sha256": (
        "a38d76010326fea29114bd3e277268ac12cdd73e4d18895102d2dd0ff0ac3b01"
    ),
    "manifest_sha256": (
        "4ec53564a3f755ea0835d4bd7fc7c89323e9a29123e68b8e5effd0e7d7074325"
    ),
}
EXPECTED_FREEZE_RECEIPT_SHA = (
    "cb04d4b24a86468a88b25c09d21b135cddc314d821558b26526c8fe91506643a"
)
EXPECTED_WINDOW_COUNTS = {1: 4, 2: 8, 3: 4, 4: 9, 5: 6, 6: 11}
EXPECTED_TOTAL_LABELS = 42

EXPECTED_SELECTION_SHA = (
    "9bdaa635b71b09287def03bd38a0a8fe3c1a50a5f0fd431ee686e685bbc369e8"
)

ALLOWED_DECISIONS = (
    "CANDIDATE_OUTPERFORMS_BASELINE_ON_AI_DRAFT",
    "BASELINE_OUTPERFORMS_CANDIDATE_ON_AI_DRAFT",
    "MIXED_AI_DRAFT_RESULT",
    "AI_DRAFT_DIAGNOSTIC_INCONCLUSIVE",
)

FORBIDDEN_DECISIONS = (
    "PROMOTE_V2_3_0_FINAL",
    "PASS_RETROSPECTIVE_ENGINEERING_GATE",
    "FAIL_RETROSPECTIVE_ENGINEERING_GATE",
    "PRODUCTION_READY",
    "RELEASE_APPROVED",
    "HUMAN_ADJUDICATED",
    "FROZEN_HUMAN_ADJUDICATED",
)

DIAGNOSTIC_WARNING = (
    "These metrics use AI-assisted engineering-draft labels. They are diagnostic "
    "only and cannot establish human benchmark performance, release approval, or "
    "production certification."
)

AI_DRAFT_EVALUATOR_TAG = "xauusd-h1-2022-2024-ai-draft-evaluator-v1"
AI_DRAFT_EVALUATOR_SCRIPT = (
    "scripts/evaluate_xauusd_h1_2022_2024_ai_assisted_engineering.py"
)

sha256 = POST.sha256
utc_now = POST.utc_now
load_samples = POST.load_samples
run_profile = POST.run_profile
prefix_audit = POST.prefix_audit
CANDIDATE_TAG = POST.CANDIDATE_TAG


def refuse_non_ai_draft_origin(value: Any, *, field: str) -> str:
    """Local AI-draft origin gate; independent of PROTECTED_ANNOTATION_ORIGINS."""
    if value is None or (isinstance(value, str) and not str(value).strip()):
        raise SystemExit(f"REFUSED: missing {field}")
    origin = str(value)
    if origin in REFUSED_LABEL_ORIGINS:
        raise SystemExit(
            f"REFUSED: {field} {origin!r} is forbidden for AI engineering draft"
        )
    if origin != AI_DRAFT_ORIGIN:
        raise SystemExit(
            f"REFUSED: {field} must be exactly {AI_DRAFT_ORIGIN}, got {origin!r}"
        )
    return origin


def refuse_non_diagnostic_eligibility(
    eligibility: dict[str, Any] | None,
    *,
    field: str = "eligibility",
) -> None:
    eligibility = eligibility or {}
    for key in (
        "eligible_for_human_benchmark",
        "human_adjudicated",
        "eligible_for_release_gate",
        "eligible_for_production_certification",
        "eligible_for_tuning",
        "prospective_test",
    ):
        if eligibility.get(key) is not False:
            raise SystemExit(f"REFUSED: {field}.{key} must be false")
    if eligibility.get("eligible_for_engineering_diagnostic") is not True:
        raise SystemExit(
            f"REFUSED: {field}.eligible_for_engineering_diagnostic must be true"
        )


def verify_repository(candidate_commit: str) -> dict[str, Any]:
    """Seal candidate, post evaluator, and this AI-draft evaluator."""
    evidence = dict(POST.verify_repository(candidate_commit))

    try:
        ai_commit = POST.git_output(
            "rev-parse",
            f"{AI_DRAFT_EVALUATOR_TAG}^{{commit}}",
        )
    except subprocess.CalledProcessError:
        raise SystemExit(
            "REFUSED: AI-draft evaluator freeze tag is missing"
        ) from None

    ai_changes = POST.git_output(
        "diff",
        "--name-only",
        f"{ai_commit}..HEAD",
        "--",
        AI_DRAFT_EVALUATOR_SCRIPT,
    )
    if ai_changes.strip():
        raise SystemExit(
            "REFUSED: AI-draft evaluator changed after its freeze tag"
        )

    evidence["ai_draft_evaluator_tag"] = AI_DRAFT_EVALUATOR_TAG
    evidence["ai_draft_evaluator_tag_commit"] = ai_commit
    return evidence


def f1_of(aggregate: dict[str, Any], key: str) -> float:
    block = aggregate.get(key) or {}
    if not isinstance(block, dict) or "f1" not in block:
        raise SystemExit(f"REFUSED: missing F1 metric for {key}")
    return float(block["f1"])


def extract_location_semantic_f1(
    aggregate: dict[str, Any],
) -> tuple[float, float]:
    if "location" in aggregate and "semantic" in aggregate:
        return f1_of(aggregate, "location"), f1_of(aggregate, "semantic")
    if "location_f1" in aggregate and "semantic_f1" in aggregate:
        return float(aggregate["location_f1"]), float(aggregate["semantic_f1"])
    raise SystemExit("REFUSED: aggregate missing location/semantic F1")


def diagnostic_conclusion(
    *,
    candidate: dict[str, Any],
    baseline: dict[str, Any],
    prefix: dict[str, Any],
) -> str:
    failures = int(prefix.get("summary", {}).get("failures", 0))
    if failures > 0:
        return "AI_DRAFT_DIAGNOSTIC_INCONCLUSIVE"

    cand_loc, cand_sem = extract_location_semantic_f1(candidate)
    base_loc, base_sem = extract_location_semantic_f1(baseline)

    cand_ge = cand_loc >= base_loc and cand_sem >= base_sem
    cand_strict = cand_loc > base_loc or cand_sem > base_sem
    base_ge = cand_loc <= base_loc and cand_sem <= base_sem
    base_strict = cand_loc < base_loc or cand_sem < base_sem

    if cand_ge and cand_strict:
        return "CANDIDATE_OUTPERFORMS_BASELINE_ON_AI_DRAFT"
    if base_ge and base_strict:
        return "BASELINE_OUTPERFORMS_CANDIDATE_ON_AI_DRAFT"
    return "MIXED_AI_DRAFT_RESULT"


def non_binding_threshold_diagnostics(
    *,
    protocol: dict[str, Any],
    candidate: dict[str, Any],
    baseline: dict[str, Any],
    prefix: dict[str, Any],
) -> dict[str, Any]:
    gates = protocol.get("engineering_gates") or protocol.get("promotion_gates") or {}
    cand_loc, cand_sem = extract_location_semantic_f1(candidate)
    base_loc, base_sem = extract_location_semantic_f1(baseline)
    return {
        "label": "NON_BINDING_AI_DRAFT_THRESHOLD_DIAGNOSTICS",
        "comparisons": {
            "prefix_stability_failures": int(
                prefix.get("summary", {}).get("failures", 0)
            ),
            "candidate_location_f1": cand_loc,
            "candidate_semantic_f1": cand_sem,
            "baseline_location_f1": base_loc,
            "baseline_semantic_f1": base_sem,
            "protocol_engineering_gates": gates,
            "note": (
                "Informational only. These comparisons do not produce a gate "
                "decision and cannot approve release or production certification."
            ),
        },
    }


def load_package(package_root: Path) -> dict[str, Any]:
    package_root = package_root.resolve()
    manifest_path = package_root / MANIFEST_FILENAME
    labels_path = package_root / LABELS_FILENAME
    data_path = package_root / DATA_FILENAME
    receipt_path = package_root / "freeze_receipt.json"

    for path in (manifest_path, labels_path, data_path, receipt_path):
        if not path.exists():
            raise SystemExit(f"REFUSED: missing frozen package file {path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    labels = json.loads(labels_path.read_text(encoding="utf-8"))
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))

    # Origin checks first so forbidden human/expert claims are explicit.
    for document, name in (
        (manifest, "manifest"),
        (labels, "labels"),
        (receipt, "receipt"),
    ):
        refuse_non_ai_draft_origin(
            document.get("label_origin"),
            field=f"{name}.label_origin",
        )

    for document, name in (
        (manifest, "manifest"),
        (labels, "labels"),
        (receipt, "receipt"),
    ):
        if document.get("status") != AI_DRAFT_STATUS:
            raise SystemExit(
                f"REFUSED: {name} status is not {AI_DRAFT_STATUS}"
            )
        if document.get("benchmark_type") != AI_DIAGNOSTIC_TYPE:
            raise SystemExit(
                f"REFUSED: {name} benchmark_type is not {AI_DIAGNOSTIC_TYPE}"
            )

    if labels.get("status") in {
        "FROZEN_HUMAN_ADJUDICATED",
        "HUMAN_ADJUDICATED",
    }:
        raise SystemExit("REFUSED: HUMAN_ADJUDICATED claim is forbidden")

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
        "candidate_evaluated",
        "baseline_evaluated",
        "predictions_loaded",
        "swing_detector_executed",
    ):
        if controls.get(key) is not False:
            raise SystemExit(
                f"REFUSED: package contamination control {key} failed"
            )
    if controls.get("labels_generated_by_ai") is not True:
        raise SystemExit("REFUSED: labels_generated_by_ai must be true")
    if controls.get("human_blind_pass_completed") is not False:
        raise SystemExit("REFUSED: human_blind_pass_completed must be false")

    refuse_non_diagnostic_eligibility(
        manifest.get("eligibility"),
        field="manifest.eligibility",
    )
    refuse_non_diagnostic_eligibility(
        labels.get("eligibility"),
        field="labels.eligibility",
    )

    samples = labels.get("samples") or []
    if len(samples) != 6:
        raise SystemExit("REFUSED: expected exactly six samples")
    swings = labels.get("swings") or []
    counts: dict[int, int] = {i: 0 for i in range(1, 7)}
    sample_by_id = {s["sample_id"]: s for s in samples}
    for swing in swings:
        sample = sample_by_id.get(swing.get("sample_id"))
        if sample is None:
            raise SystemExit("REFUSED: swing references unknown sample")
        counts[int(sample["window_number"])] += 1

    # Real frozen package: exact published counts and output hashes.
    if actual == EXPECTED_PACKAGE_OUTPUTS:
        if len(swings) != EXPECTED_TOTAL_LABELS:
            raise SystemExit(
                f"REFUSED: expected {EXPECTED_TOTAL_LABELS} labels, "
                f"found {len(swings)}"
            )
        if counts != EXPECTED_WINDOW_COUNTS:
            raise SystemExit(
                f"REFUSED: unexpected per-window label counts {counts}"
            )
        if sha256(receipt_path) != EXPECTED_FREEZE_RECEIPT_SHA:
            raise SystemExit("REFUSED: freeze receipt SHA-256 mismatch")
    elif not swings:
        raise SystemExit("REFUSED: package contains no swings")

    selection_meta = receipt["source_evidence"]["selection_manifest"]
    selection_path = Path(selection_meta["path"])
    if not selection_path.is_absolute():
        selection_path = (ROOT / selection_path).resolve()
    if sha256(selection_path) != EXPECTED_SELECTION_SHA:
        raise SystemExit("REFUSED: selection-manifest hash mismatch")
    if selection_meta.get("sha256") != EXPECTED_SELECTION_SHA:
        raise SystemExit("REFUSED: receipt selection hash mismatch")

    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    selection_root = selection_path.parent
    for window in selection["windows"]:
        path = selection_root / str(window["file"])
        if sha256(path) != window["sha256"]:
            raise SystemExit(
                f"REFUSED: source window hash mismatch for {window['file']}"
            )
        expected_window = receipt["source_evidence"]["windows"].get(
            str(window["file"])
        )
        if expected_window != window["sha256"]:
            raise SystemExit(
                f"REFUSED: receipt window hash mismatch for {window['file']}"
            )

    protocol_meta = receipt["source_evidence"]["protocol"]
    protocol_path = Path(protocol_meta["path"])
    if not protocol_path.is_absolute():
        protocol_path = (ROOT / protocol_path).resolve()
    if sha256(protocol_path) != protocol_meta["sha256"]:
        raise SystemExit("REFUSED: protocol checksum mismatch")
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    if protocol.get("protocol_id") != PROTOCOL_ID:
        raise SystemExit("REFUSED: unexpected protocol_id")
    if manifest.get("protocol_id") != PROTOCOL_ID:
        raise SystemExit("REFUSED: manifest protocol_id mismatch")

    candidate = protocol["candidate"]
    baseline = protocol["baseline"]
    if receipt.get("candidate") != candidate:
        raise SystemExit("REFUSED: candidate metadata mismatch")
    if receipt.get("baseline") != baseline:
        raise SystemExit("REFUSED: baseline metadata mismatch")

    from swing_engine.datasets import load_manifest

    specs = load_manifest(manifest_path)
    if len(specs) != 6:
        raise SystemExit("REFUSED: expected six TEST windows")
    if any(spec.split.upper() != "TEST" for spec in specs):
        raise SystemExit("REFUSED: frozen manifest contains a non-TEST sample")

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
    if output_root == package_root or package_root in output_root.parents:
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
    diagnostic_path = output_root / DIAGNOSTIC_NAME

    samples = load_samples(package["specs"], package["manifest_path"])

    output_root.mkdir(parents=True)
    started_at = utc_now()

    unblinding = {
        "dataset_id": package["manifest"]["dataset_id"],
        "protocol_id": PROTOCOL_ID,
        "benchmark_type": BENCHMARK_TYPE,
        "label_origin": LABEL_ORIGIN,
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
            "release_gate": False,
            "production_certification": False,
        },
        "warning": DIAGNOSTIC_WARNING,
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

    conclusion = diagnostic_conclusion(
        candidate=candidate,
        baseline=baseline,
        prefix=prefix,
    )
    if conclusion not in ALLOWED_DECISIONS:
        raise SystemExit(
            f"REFUSED: illegal diagnostic conclusion {conclusion}"
        )
    if conclusion in FORBIDDEN_DECISIONS:
        raise SystemExit(
            "REFUSED: forbidden promotion/release decision emitted"
        )

    thresholds = non_binding_threshold_diagnostics(
        protocol=protocol,
        candidate=candidate,
        baseline=baseline,
        prefix=prefix,
    )

    completed_at = utc_now()
    report = {
        "dataset_id": package["manifest"]["dataset_id"],
        "protocol_id": PROTOCOL_ID,
        "benchmark_type": BENCHMARK_TYPE,
        "label_origin": LABEL_ORIGIN,
        "benchmark_status": PACKAGE_STATUS,
        "started_at_utc": started_at,
        "completed_at_utc": completed_at,
        "warning": DIAGNOSTIC_WARNING,
        "diagnostic_conclusion": conclusion,
        "allowed_diagnostic_conclusions": list(ALLOWED_DECISIONS),
        "forbidden_decision_values": list(FORBIDDEN_DECISIONS),
        "non_binding_threshold_diagnostics": thresholds,
        "candidate": {
            "version": candidate_label,
            "engine_version": candidate_version,
            "aggregate": candidate,
            "per_window": candidate_rows,
        },
        "baseline": {
            "version": baseline_version,
            "aggregate": baseline,
            "per_window": baseline_rows,
        },
        "prefix_stability": prefix,
        "repository": repository,
        "package_hashes": package["hashes"],
        "gate_decision": None,
        "release_decision": None,
        "production_certification": False,
    }
    report_path.write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )

    unblinding["state"] = "UNBLINDING_COMPLETE"
    unblinding["completed_at_utc"] = completed_at
    unblinding["diagnostic_conclusion"] = conclusion
    unblinding_path.write_text(
        json.dumps(unblinding, indent=2) + "\n",
        encoding="utf-8",
    )

    diagnostic = {
        "dataset_id": package["manifest"]["dataset_id"],
        "protocol_id": PROTOCOL_ID,
        "benchmark_type": BENCHMARK_TYPE,
        "label_origin": LABEL_ORIGIN,
        "status": "AI_DRAFT_DIAGNOSTIC_COMPLETE",
        "diagnostic_conclusion": conclusion,
        "allowed_diagnostic_conclusions": list(ALLOWED_DECISIONS),
        "forbidden_decision_values": list(FORBIDDEN_DECISIONS),
        "non_binding_threshold_diagnostics": thresholds,
        "warning": DIAGNOSTIC_WARNING,
        "gate_decision": None,
        "release_decision": None,
        "production_certification": False,
        "completed_at_utc": completed_at,
        "package_hashes": package["hashes"],
        "repository": repository,
    }
    diagnostic_path.write_text(
        json.dumps(diagnostic, indent=2) + "\n",
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "output_root": str(output_root),
                "diagnostic_conclusion": conclusion,
                "warning": DIAGNOSTIC_WARNING,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

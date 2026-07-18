#!/usr/bin/env python3
"""Run the one-time XAUUSD H1 2026H1 locked TEST evaluation."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from swing_engine.datasets import load_manifest  # noqa: E402


DATASET_ID = "XAUUSD_H1_2026H1_LOCKED_TEST_V1"
EXPECTED_FROZEN_COMMIT = "a543e5e"

ENGINE_VERSION = "2.2.0"
HIERARCHY_REVERSAL_ATR = 5.0
PROVISIONAL_PROMINENCE_ATR = 5.0

MANIFEST_PATH = (
    ROOT
    / "benchmarks"
    / "datasets"
    / "XAUUSD_H1_2026H1.human.manifest.json"
)
LABELS_PATH = (
    ROOT
    / "benchmarks"
    / "labels"
    / "XAUUSD_H1_2026H1.human.json"
)
FREEZE_RECEIPT_PATH = (
    ROOT
    / "benchmarks"
    / "reports"
    / "XAUUSD_H1_2026H1_labels_freeze_receipt.json"
)
OUTPUT_PATH = (
    ROOT
    / "benchmarks"
    / "reports"
    / "XAUUSD_H1_2026H1_v2_2_locked_test.json"
)
UNBLINDING_RECEIPT_PATH = (
    ROOT
    / "benchmarks"
    / "reports"
    / "XAUUSD_H1_2026H1_v2_2_unblinding_receipt.json"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def current_git_head() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
    ).strip()


def load_development_helpers():
    """Load evaluation helpers without invoking the tuning command."""
    module_path = ROOT / "scripts" / "tune_xauusd_h1_hierarchy.py"

    spec = importlib.util.spec_from_file_location(
        "fxnavigators_hierarchy_evaluation_helpers",
        module_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {module_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    if OUTPUT_PATH.exists() or UNBLINDING_RECEIPT_PATH.exists():
        raise SystemExit(
            "REFUSED: this locked evaluation has already been started "
            "or completed."
        )

    git_head = current_git_head()
    if not git_head.startswith(EXPECTED_FROZEN_COMMIT):
        raise SystemExit(
            "REFUSED: HEAD is not the frozen pre-unblinding commit.\n"
            f"Expected: {EXPECTED_FROZEN_COMMIT}\n"
            f"Actual:   {git_head}"
        )

    manifest_document = json.loads(
        MANIFEST_PATH.read_text(encoding="utf-8")
    )
    labels_document = json.loads(
        LABELS_PATH.read_text(encoding="utf-8")
    )
    freeze_receipt = json.loads(
        FREEZE_RECEIPT_PATH.read_text(encoding="utf-8")
    )

    if manifest_document.get("dataset_id") != DATASET_ID:
        raise SystemExit("REFUSED: manifest dataset ID mismatch")

    if labels_document.get("benchmark_id") != DATASET_ID:
        raise SystemExit("REFUSED: label benchmark ID mismatch")

    if manifest_document.get("status") != "FROZEN_AI_DRAFT":
        raise SystemExit("REFUSED: manifest is not frozen")

    if labels_document.get("status") != "FROZEN_AI_DRAFT":
        raise SystemExit("REFUSED: label file is not frozen")

    actual_labels_sha = sha256(LABELS_PATH)
    expected_labels_sha = freeze_receipt["labels_sha256"]

    if actual_labels_sha != expected_labels_sha:
        raise SystemExit(
            "REFUSED: frozen label checksum changed.\n"
            f"Expected: {expected_labels_sha}\n"
            f"Actual:   {actual_labels_sha}"
        )

    specs = load_manifest(MANIFEST_PATH)

    if len(specs) != 6:
        raise SystemExit(
            f"REFUSED: expected 6 TEST samples, found {len(specs)}"
        )

    if any(spec.split.upper() != "TEST" for spec in specs):
        raise SystemExit("REFUSED: manifest contains a non-TEST sample")

    expected_data_sha = freeze_receipt["data_sha256"]

    for spec in specs:
        data_path = ROOT / "benchmarks" / Path(spec.data_file)

        actual_data_sha = sha256(data_path)
        if actual_data_sha != expected_data_sha:
            raise SystemExit(
                f"REFUSED: candle checksum mismatch for {spec.id}\n"
                f"Expected: {expected_data_sha}\n"
                f"Actual:   {actual_data_sha}"
            )

    helpers = load_development_helpers()

    # Loading raw bars and frozen labels does not generate predictions.
    samples = {
        spec.id: helpers._load_sample(spec, MANIFEST_PATH)
        for spec in specs
    }

    started_at = datetime.now(timezone.utc).isoformat(
        timespec="seconds"
    )

    # Write the irreversible unblinding marker immediately before detection.
    unblinding_receipt = {
        "dataset_id": DATASET_ID,
        "state": "UNBLINDING_STARTED",
        "started_at": started_at,
        "frozen_commit": git_head,
        "engine_version": ENGINE_VERSION,
        "hierarchy_reversal_atr": HIERARCHY_REVERSAL_ATR,
        "provisional_prominence_atr": PROVISIONAL_PROMINENCE_ATR,
        "labels_sha256": actual_labels_sha,
        "data_sha256": expected_data_sha,
        "sample_count": len(specs),
        "policy": (
            "One-time locked TEST evaluation. "
            "No parameter selection or tuning."
        ),
    }

    UNBLINDING_RECEIPT_PATH.write_text(
        json.dumps(unblinding_receipt, indent=2) + "\n",
        encoding="utf-8",
    )

    rows = helpers._run_profile(
        specs,
        samples,
        version=ENGINE_VERSION,
        hierarchy_reversal_atr=HIERARCHY_REVERSAL_ATR,
        provisional_prominence_atr=PROVISIONAL_PROMINENCE_ATR,
    )

    # Correct legacy development-only metadata returned by the helper.
    for row in rows:
        row["benchmark_version"] = DATASET_ID

    aggregate = helpers._aggregate(rows)
    by_regime = helpers._aggregate_by_regime(rows)

    completed_at = datetime.now(timezone.utc).isoformat(
        timespec="seconds"
    )

    payload = {
        "dataset_id": DATASET_ID,
        "benchmark_status": "FROZEN_AI_DRAFT",
        "warning": (
            "Labels are a blind AI-assisted expert draft and still require "
            "independent human adjudication before production certification."
        ),
        "evaluation_policy": {
            "split": "TEST",
            "run_policy": "ONE_TIME_LOCKED_EVALUATION",
            "parameter_selection": "NONE",
            "predictions_hidden_during_labeling": True,
            "frozen_commit": git_head,
            "labels_sha256": actual_labels_sha,
            "data_sha256": expected_data_sha,
        },
        "engine": {
            "version": ENGINE_VERSION,
            "hierarchy_reversal_atr": HIERARCHY_REVERSAL_ATR,
            "provisional_prominence_atr": (
                PROVISIONAL_PROMINENCE_ATR
            ),
        },
        "started_at": started_at,
        "completed_at": completed_at,
        "aggregate": aggregate,
        "by_regime": by_regime,
        "per_sample": rows,
    }

    OUTPUT_PATH.write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )

    unblinding_receipt.update({
        "state": "COMPLETED",
        "completed_at": completed_at,
        "report": str(OUTPUT_PATH.relative_to(ROOT)),
        "report_sha256": sha256(OUTPUT_PATH),
    })

    UNBLINDING_RECEIPT_PATH.write_text(
        json.dumps(unblinding_receipt, indent=2) + "\n",
        encoding="utf-8",
    )

    print()
    print("ONE-TIME LOCKED TEST COMPLETE")
    print("=" * 72)
    print(json.dumps({
        "engine_version": ENGINE_VERSION,
        "samples": len(specs),
        "predicted": aggregate["predicted"],
        "ground_truth": aggregate["ground_truth"],
        "location": aggregate["location"],
        "semantic": aggregate["semantic"],
        "major_external": aggregate["major_external"],
    }, indent=2))

    print()
    print("PER SAMPLE")
    print("=" * 72)

    for row in rows:
        print(
            f"{row['sample_id']} | "
            f"pred={row['predicted']} "
            f"truth={row['ground_truth']} "
            f"location_f1={row['f1_score']:.6f} "
            f"semantic_f1={row['semantic_f1']:.6f}"
        )

    print()
    print(f"Report:  {OUTPUT_PATH}")
    print(f"Receipt: {UNBLINDING_RECEIPT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

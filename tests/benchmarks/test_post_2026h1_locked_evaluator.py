"""Tests for the one-time post-2026H1 locked evaluator."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def load_script(filename: str, module_name: str):
    path = ROOT / "scripts" / filename

    spec = importlib.util.spec_from_file_location(
        module_name,
        path,
    )

    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


EVALUATOR = load_script(
    "evaluate_xauusd_h1_post_2026h1_locked.py",
    "test_post_2026h1_locked_evaluator",
)


from shared.types.models import Candle, Timeframe  # noqa: E402
from swing_engine.benchmark_data import (  # noqa: E402
    write_canonical_candles_csv,
)


CANDIDATE_COMMIT = (
    "3fd5d7c74b82c3728d7badaa6cd72044bdd6bd1d"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


def write_json(
    path: Path,
    value: dict,
) -> Path:
    path.write_text(
        json.dumps(value, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def promotion_gates() -> dict:
    return {
        "prefix_stability_failures_max": 0,
        "location_precision_min": 0.80,
        "location_recall_min": 0.70,
        "location_f1_min": 0.75,
        "semantic_f1_min": 0.60,
        "major_external_precision_min": 0.85,
        "major_external_recall_min": 0.40,
        "worst_window_location_f1_min": 0.50,
        (
            "candidate_location_f1_"
            "delta_vs_v2_2_min"
        ): 0.00,
        (
            "candidate_semantic_f1_"
            "delta_vs_v2_2_min"
        ): 0.00,
    }


def create_frozen_package(
    tmp_path: Path,
) -> Path:
    package = tmp_path / "frozen-package"
    package.mkdir()

    protocol_path = tmp_path / "protocol.json"

    protocol = {
        "protocol_id": "SYNTHETIC_LOCKED_PROTOCOL",
        "candidate": {
            "version": "2.3.0-rc1",
            "commit": CANDIDATE_COMMIT,
        },
        "baseline": {
            "version": "2.2.0",
        },
        "window_selection": {
            "bucket_count": 2,
            "window_bars": 80,
        },
        "evaluation": {
            "candidate_evaluations_allowed": 1,
            "baseline_evaluations_allowed": 1,
            "error_analysis_before_release_decision": False,
            "tuning_after_unblinding": False,
            "prefix_stability_required": True,
        },
        "promotion_gates": promotion_gates(),
    }

    write_json(protocol_path, protocol)

    data_path = (
        package
        / (
            "XAUUSD_H1_post_2026H1_locked."
            "real.csv.gz"
        )
    )
    labels_path = (
        package
        / (
            "XAUUSD_H1_post_2026H1_locked."
            "human.json"
        )
    )
    manifest_path = (
        package
        / (
            "XAUUSD_H1_post_2026H1_locked."
            "human.manifest.json"
        )
    )
    receipt_path = (
        package / "freeze_receipt.json"
    )

    start = datetime(
        2026,
        10,
        1,
        tzinfo=timezone.utc,
    )

    candles = []

    for index in range(160):
        wave = (
            8.0
            if (index // 10) % 2 == 0
            else -8.0
        )

        base = (
            4000.0
            + index * 0.08
            + wave
        )

        candles.append(
            Candle(
                symbol="XAUUSD",
                timeframe=Timeframe.H1,
                timestamp=(
                    start
                    + timedelta(hours=index)
                ),
                open=base,
                high=base + 2.5,
                low=base - 2.5,
                close=base + 0.4,
                volume=0,
                tick_volume=1000 + index,
                spread=0.29,
            )
        )

    write_canonical_candles_csv(
        data_path,
        candles,
        source="SYNTHETIC_LOCKED_TEST",
        price_basis="MID",
    )

    data_sha = sha256(data_path)

    sample_ids = [
        "XAUUSD_H1_POST_2026H1_001",
        "XAUUSD_H1_POST_2026H1_002",
    ]

    samples = [
        {
            "sample_id": sample_ids[0],
            "window_number": 1,
            "split": "TEST",
            "source_start_index": 0,
            "source_end_index": 79,
            "labelable_start_index": 0,
            "labelable_end_index": 79,
            "bars": 80,
            "start_timestamp": (
                candles[0]
                .timestamp
                .isoformat()
            ),
            "end_timestamp": (
                candles[79]
                .timestamp
                .isoformat()
            ),
        },
        {
            "sample_id": sample_ids[1],
            "window_number": 2,
            "split": "TEST",
            "source_start_index": 80,
            "source_end_index": 159,
            "labelable_start_index": 0,
            "labelable_end_index": 79,
            "bars": 80,
            "start_timestamp": (
                candles[80]
                .timestamp
                .isoformat()
            ),
            "end_timestamp": (
                candles[159]
                .timestamp
                .isoformat()
            ),
        },
    ]

    swings = []

    decisions = [
        (sample_ids[0], 0, 20, "HIGH", 25, "MAJOR", "EXTERNAL"),
        (sample_ids[0], 0, 50, "LOW", 55, "MINOR", "INTERNAL"),
        (sample_ids[1], 80, 20, "HIGH", 25, "MAJOR", "EXTERNAL"),
        (sample_ids[1], 80, 50, "LOW", 55, "MINOR", "INTERNAL"),
    ]

    for number, (
        sample_id,
        source_start,
        pivot_index,
        direction,
        confirmation_index,
        tier,
        scope,
    ) in enumerate(decisions, start=1):
        pivot = candles[
            source_start + pivot_index
        ]
        confirmation = candles[
            source_start + confirmation_index
        ]

        swings.append(
            {
                "label_id": (
                    f"SYNTHETIC_SWG_{number:03d}"
                ),
                "sample_id": sample_id,
                "pivot_index": pivot_index,
                "source_bar_index": (
                    source_start + pivot_index
                ),
                "timestamp": (
                    pivot.timestamp.isoformat()
                ),
                "price": (
                    pivot.high
                    if direction == "HIGH"
                    else pivot.low
                ),
                "price_field": direction,
                "direction": direction,
                "tier": tier,
                "scope": scope,
                "confirmation_status": (
                    "ADJUDICATED"
                ),
                "confirmed_at_index": (
                    confirmation_index
                ),
                "confirmed_at_timestamp": (
                    confirmation
                    .timestamp
                    .isoformat()
                ),
                "tags": [
                    "HUMAN_ADJUDICATED",
                    "BLIND_TWO_PASS",
                ],
                "notes": "",
                "annotator_id": "SYNTHETIC",
                "review_status": "ADJUDICATED",
            }
        )

    labels = {
        "benchmark_id": (
            "SYNTHETIC_LOCKED_PROTOCOL"
        ),
        "benchmark_version": (
            "1.0.0-locked-human-adjudicated"
        ),
        "label_policy_version": (
            "SYNTHETIC_LOCKED_PROTOCOL"
        ),
        "label_origin": "HUMAN_ADJUDICATED",
        "status": (
            "FROZEN_HUMAN_ADJUDICATED"
        ),
        "dataset": {
            "dataset_id": (
                "SYNTHETIC_LOCKED_PROTOCOL"
            ),
            "symbol": "XAUUSD",
            "timeframe": "H1",
            "timezone": "UTC",
            "price_basis": "MID",
            "source": (
                "SYNTHETIC_LOCKED_TEST"
            ),
            "data_file": data_path.name,
            "data_sha256": data_sha,
            "bar_count": 160,
            "first_timestamp": (
                candles[0]
                .timestamp
                .isoformat()
            ),
            "last_timestamp": (
                candles[-1]
                .timestamp
                .isoformat()
            ),
        },
        "samples": samples,
        "swings": swings,
        "review": {
            "required_annotators": 2,
            "adjudicator": "SYNTHETIC",
            "prediction_visibility": (
                "HIDDEN_UNTIL_LABEL_FREEZE"
            ),
            "engine_version_visibility": (
                "HIDDEN_UNTIL_LABEL_FREEZE"
            ),
        },
    }

    write_json(labels_path, labels)
    labels_sha = sha256(labels_path)

    datasets = []

    for sample in samples:
        datasets.append(
            {
                "id": sample["sample_id"],
                "sample_id": (
                    sample["sample_id"]
                ),
                "symbol": "XAUUSD",
                "timeframe": "H1",
                "regime": "unknown",
                "bars": sample["bars"],
                "labels_file": labels_path.name,
                "human_review": True,
                "label_source": (
                    "HUMAN_ADJUDICATED"
                ),
                "evaluation_tolerance_bars": 0,
                "description": (
                    "Synthetic frozen TEST window"
                ),
                "source_type": "real",
                "data_file": data_path.name,
                "data_sha256": data_sha,
                "source_start_index": (
                    sample["source_start_index"]
                ),
                "source_end_index": (
                    sample["source_end_index"]
                ),
                "labelable_start_index": 0,
                "labelable_end_index": 79,
                "split": "TEST",
                "label_origin": (
                    "HUMAN_ADJUDICATED"
                ),
                "enabled": True,
            }
        )

    manifest = {
        "manifest_version": "1.0",
        "dataset_id": (
            "SYNTHETIC_LOCKED_PROTOCOL"
        ),
        "protocol_id": (
            "SYNTHETIC_LOCKED_PROTOCOL"
        ),
        "status": (
            "FROZEN_UNBLINDED_LABELS_"
            "NOT_EVALUATED"
        ),
        "path_resolution": (
            "PACKAGE_RELATIVE"
        ),
        "candidate": protocol["candidate"],
        "baseline": protocol["baseline"],
        "files": {
            "data": {
                "path": data_path.name,
                "sha256": data_sha,
            },
            "labels": {
                "path": labels_path.name,
                "sha256": labels_sha,
            },
        },
        "datasets": datasets,
        "contamination_controls": {
            "predictions_loaded": False,
            "swing_detector_executed": False,
            "candidate_evaluated": False,
            "baseline_evaluated": False,
        },
    }

    write_json(manifest_path, manifest)
    manifest_sha = sha256(manifest_path)

    receipt = {
        "dataset_id": (
            "SYNTHETIC_LOCKED_PROTOCOL"
        ),
        "protocol_id": (
            "SYNTHETIC_LOCKED_PROTOCOL"
        ),
        "status": (
            "FROZEN_HUMAN_ADJUDICATED_"
            "NOT_EVALUATED"
        ),
        "candidate": protocol["candidate"],
        "baseline": protocol["baseline"],
        "source_evidence": {
            "protocol": {
                "path": str(
                    protocol_path.resolve()
                ),
                "sha256": sha256(
                    protocol_path
                ),
            },
        },
        "outputs": {
            "data_sha256": data_sha,
            "labels_sha256": labels_sha,
            "manifest_sha256": (
                manifest_sha
            ),
        },
    }

    write_json(receipt_path, receipt)
    return package


def passing_candidate() -> dict:
    return {
        "location": {
            "precision": 0.90,
            "recall": 0.80,
            "f1": 0.847059,
        },
        "semantic": {
            "f1": 0.70,
        },
        "major_external": {
            "precision": 0.90,
            "recall": 0.50,
        },
    }


def passing_baseline() -> dict:
    return {
        "location": {
            "f1": 0.80,
        },
        "semantic": {
            "f1": 0.65,
        },
    }


def test_release_gate_passes_only_when_every_threshold_passes():
    protocol = {
        "promotion_gates": promotion_gates(),
    }

    candidate_rows = [
        {"f1_score": 0.70},
        {"f1_score": 0.90},
    ]

    prefix = {
        "summary": {
            "failures": 0,
        },
    }

    receipt = EVALUATOR.gate_receipt(
        protocol=protocol,
        candidate=passing_candidate(),
        baseline=passing_baseline(),
        candidate_rows=candidate_rows,
        prefix=prefix,
    )

    assert receipt["status"] == "PASS"
    assert receipt["decision"] == (
        "PROMOTE_V2_3_0_FINAL"
    )
    assert receipt[
        "all_gates_passed"
    ] is True
    assert all(
        check["passed"]
        for check in receipt["checks"]
    )


def test_release_gate_fails_on_one_failed_threshold():
    protocol = {
        "promotion_gates": promotion_gates(),
    }

    candidate = passing_candidate()
    candidate["location"]["recall"] = 0.60

    receipt = EVALUATOR.gate_receipt(
        protocol=protocol,
        candidate=candidate,
        baseline=passing_baseline(),
        candidate_rows=[
            {"f1_score": 0.70},
            {"f1_score": 0.90},
        ],
        prefix={
            "summary": {
                "failures": 0,
            },
        },
    )

    assert receipt["status"] == "FAIL"
    assert receipt["decision"] == (
        "REMAIN_V2_3_0_RC1"
    )

    failed = [
        check
        for check in receipt["checks"]
        if not check["passed"]
    ]

    assert [
        check["gate"]
        for check in failed
    ] == [
        "location_recall_min"
    ]


def test_package_checksum_tampering_is_refused(
    tmp_path: Path,
):
    package = create_frozen_package(
        tmp_path
    )

    labels_path = (
        package
        / (
            "XAUUSD_H1_post_2026H1_locked."
            "human.json"
        )
    )

    labels_path.write_text(
        labels_path.read_text(
            encoding="utf-8"
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        SystemExit,
        match=(
            "frozen package checksum mismatch"
        ),
    ):
        EVALUATOR.load_package(package)


def test_one_time_evaluation_writes_all_receipts_and_refuses_rerun(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    package = create_frozen_package(
        tmp_path
    )

    output = tmp_path / "evaluation"

    monkeypatch.setattr(
        EVALUATOR,
        "verify_repository",
        lambda candidate_commit: {
            "evaluation_head": "TEST_HEAD",
            "candidate_tag":
                EVALUATOR.CANDIDATE_TAG,
            "candidate_tag_commit":
                candidate_commit,
            "allowed_post_candidate_changes": [],
        },
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "evaluator",
            "--package-root",
            str(package),
            "--output-root",
            str(output),
        ],
    )

    assert EVALUATOR.main() == 0

    report_path = (
        output / EVALUATOR.REPORT_NAME
    )
    unblinding_path = (
        output / EVALUATOR.UNBLINDING_NAME
    )
    gate_path = (
        output / EVALUATOR.GATE_NAME
    )

    for path in (
        report_path,
        unblinding_path,
        gate_path,
    ):
        assert path.exists()

    report = json.loads(
        report_path.read_text(
            encoding="utf-8"
        )
    )

    assert report["candidate"][
        "engine_version"
    ] == "2.3.0"

    assert report["baseline"][
        "engine_version"
    ] == "2.2.0"

    assert report["evaluation_policy"][
        "parameter_selection"
    ] == "NONE"

    assert report["candidate"][
        "prefix_stability"
    ]["summary"]["failures"] >= 0

    unblinding = json.loads(
        unblinding_path.read_text(
            encoding="utf-8"
        )
    )

    assert unblinding["state"] == "COMPLETED"
    assert unblinding[
        "report_sha256"
    ] == sha256(report_path)

    gate = json.loads(
        gate_path.read_text(
            encoding="utf-8"
        )
    )

    assert gate["status"] in {
        "PASS",
        "FAIL",
    }

    assert gate["decision"] in {
        "PROMOTE_V2_3_0_FINAL",
        "REMAIN_V2_3_0_RC1",
    }

    with pytest.raises(
        SystemExit,
        match=(
            "one-time evaluation output "
            "already exists"
        ),
    ):
        EVALUATOR.main()


def test_unblinding_marker_survives_detection_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    package = create_frozen_package(
        tmp_path
    )

    output = (
        tmp_path
        / "failed-evaluation"
    )

    monkeypatch.setattr(
        EVALUATOR,
        "verify_repository",
        lambda candidate_commit: {
            "evaluation_head": "TEST_HEAD",
            "candidate_tag":
                EVALUATOR.CANDIDATE_TAG,
            "candidate_tag_commit":
                candidate_commit,
            "allowed_post_candidate_changes": [],
        },
    )

    def fail_profile(*args, **kwargs):
        raise RuntimeError(
            "synthetic detection failure"
        )

    monkeypatch.setattr(
        EVALUATOR,
        "run_profile",
        fail_profile,
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "evaluator",
            "--package-root",
            str(package),
            "--output-root",
            str(output),
        ],
    )

    with pytest.raises(
        RuntimeError,
        match="synthetic detection failure",
    ):
        EVALUATOR.main()

    unblinding_path = (
        output / EVALUATOR.UNBLINDING_NAME
    )

    assert unblinding_path.exists()

    receipt = json.loads(
        unblinding_path.read_text(
            encoding="utf-8"
        )
    )

    assert receipt["state"] == (
        "UNBLINDING_STARTED"
    )

    assert not (
        output / EVALUATOR.REPORT_NAME
    ).exists()

    with pytest.raises(
        SystemExit,
        match=(
            "one-time evaluation output "
            "already exists"
        ),
    ):
        EVALUATOR.main()

def test_verify_repository_refuses_dependency_hash_mismatch(
    monkeypatch: pytest.MonkeyPatch,
):
    def fake_git_output(*args: str) -> str:
        if args == (
            "status",
            "--porcelain",
        ):
            return ""

        if args == (
            "rev-list",
            "-n",
            "1",
            EVALUATOR.CANDIDATE_TAG,
        ):
            return CANDIDATE_COMMIT

        if args == (
            "rev-parse",
            (
                f"{EVALUATOR.EVALUATOR_TAG}"
                "^{commit}"
            ),
        ):
            return "EVALUATOR_COMMIT"

        if (
            args[:3]
            == (
                "diff",
                "--name-only",
                "EVALUATOR_COMMIT..HEAD",
            )
        ):
            return ""

        if (
            args[:3]
            == (
                "diff",
                "--name-only",
                f"{CANDIDATE_COMMIT}..HEAD",
            )
        ):
            return "swing_engine/datasets.py"

        if args == (
            "rev-parse",
            "HEAD",
        ):
            return "TEST_HEAD"

        raise AssertionError(args)

    def fake_sha256(path: Path) -> str:
        relative = str(
            path.relative_to(ROOT)
        )

        if relative == (
            "swing_engine/datasets.py"
        ):
            return "tampered"

        return (
            EVALUATOR
            .PINNED_DEPENDENCY_SHA256[
                relative
            ]
        )

    monkeypatch.setattr(
        EVALUATOR,
        "git_output",
        fake_git_output,
    )
    monkeypatch.setattr(
        EVALUATOR,
        "sha256",
        fake_sha256,
    )

    with pytest.raises(
        SystemExit,
        match=(
            "pinned evaluation dependency "
            "changed"
        ),
    ):
        EVALUATOR.verify_repository(
            CANDIDATE_COMMIT
        )


def test_output_root_cannot_modify_frozen_package(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    package = create_frozen_package(
        tmp_path
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "evaluator",
            "--package-root",
            str(package),
            "--output-root",
            str(package / "evaluation"),
        ],
    )

    with pytest.raises(
        SystemExit,
        match=(
            "output root must be outside "
            "the immutable frozen package"
        ),
    ):
        EVALUATOR.main()

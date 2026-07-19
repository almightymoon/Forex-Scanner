"""End-to-end tests for the post-2026H1 final label freezer."""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def load_module(
    path: Path,
    module_name: str,
):
    spec = importlib.util.spec_from_file_location(
        module_name,
        path,
    )

    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


FREEZER = load_module(
    ROOT
    / "scripts"
    / "freeze_xauusd_h1_post_2026h1_labels.py",
    "test_post_2026h1_freezer",
)

HELPERS = load_module(
    ROOT
    / "tests"
    / "benchmarks"
    / "test_post_2026h1_label_passes.py",
    "test_post_2026h1_freezer_helpers",
)

PASSES = FREEZER.PASSES
ADJUDICATION = FREEZER.ADJUDICATION


from swing_engine.annotations import (  # noqa: E402
    validate_annotation_document,
)
from swing_engine.datasets import (  # noqa: E402
    _labels_path,
    load_labels,
    load_manifest,
    load_real_bars,
    resolve_data_path,
)


def write_json(
    path: Path,
    value: dict,
) -> Path:
    path.write_text(
        json.dumps(value, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def create_sources(
    tmp_path: Path,
) -> dict[str, Path]:
    selection_root = (
        HELPERS.create_selection_root(
            tmp_path,
            window_count=2,
            bars_per_window=8,
        )
    )

    selection_manifest_path = (
        selection_root
        / "selection_manifest.json"
    )

    selection = json.loads(
        selection_manifest_path.read_text(
            encoding="utf-8"
        )
    )

    protocol_id = selection["protocol_id"]

    protocol_path = (
        tmp_path / "locked_protocol.json"
    )

    protocol = {
        "protocol_id": protocol_id,
        "candidate": {
            "version": "2.3.0-rc1",
            "commit": (
                "3fd5d7c74b82c3728d7badaa6cd72044bdd6bd1d"
            ),
        },
        "baseline": {
            "version": "2.2.0",
        },
        "labeling": {
            "predictions_visible_to_labeler": False,
            "engine_version_visible_to_labeler": False,
            "passes": 2,
            "minimum_days_between_passes": 3,
            "conflicts_require_explicit_adjudication": True,
            "bars_and_labels_frozen_before_evaluation": True,
        },
    }

    write_json(
        protocol_path,
        protocol,
    )

    selection["protocol"] = {
        "path": str(protocol_path.resolve()),
        "sha256": PASSES.sha256(
            protocol_path
        ),
    }

    write_json(
        selection_manifest_path,
        selection,
    )

    first_created = datetime(
        2026,
        10,
        2,
        12,
        tzinfo=timezone.utc,
    )
    first_completed = (
        first_created
        + timedelta(hours=1)
    )

    second_created = (
        first_completed
        + timedelta(days=3)
    )
    second_completed = (
        second_created
        + timedelta(hours=1)
    )

    first_labels = [
        HELPERS.label(
            "P1_W1_HIGH",
            window_number=1,
            pivot_index=1,
            direction="HIGH",
            tier="MAJOR",
            scope="EXTERNAL",
            confirmed_at_index=2,
        ),
        HELPERS.label(
            "P1_W1_LOW",
            window_number=1,
            pivot_index=4,
            direction="LOW",
            tier="MINOR",
            scope="INTERNAL",
            confirmed_at_index=5,
        ),
        HELPERS.label(
            "P1_W2_HIGH",
            window_number=2,
            pivot_index=2,
            direction="HIGH",
            tier="MAJOR",
            scope="INTERNAL",
            confirmed_at_index=3,
        ),
    ]

    second_labels = [
        {
            **label,
            "label_id": label[
                "label_id"
            ].replace("P1_", "P2_"),
        }
        for label in first_labels
    ]

    pass_one_document = (
        HELPERS.completed_document(
            selection_root,
            pass_number=1,
            annotator_id="ANNOTATOR_A",
            created_at=first_created,
            completed_at=first_completed,
            labels=first_labels,
        )
    )

    pass_two_document = (
        HELPERS.completed_document(
            selection_root,
            pass_number=2,
            annotator_id="ANNOTATOR_B",
            created_at=second_created,
            completed_at=second_completed,
            labels=second_labels,
        )
    )

    pass_one_path = write_json(
        tmp_path / "pass_1.json",
        pass_one_document,
    )
    pass_two_path = write_json(
        tmp_path / "pass_2.json",
        pass_two_document,
    )

    first = PASSES.load_and_validate_pass(
        pass_one_path,
        selection_root=selection_root,
    )
    second = PASSES.load_and_validate_pass(
        pass_two_path,
        selection_root=selection_root,
    )

    comparison_result = (
        PASSES.compare_passes(
            first,
            second,
            minimum_days=3,
        )
    )

    assert comparison_result[
        "conflicts"
    ] == []

    comparison_document = {
        "schema_version":
            PASSES.COMPARISON_SCHEMA,
        "protocol_id": protocol_id,
        "selection_manifest_sha256":
            first[
                "selection_manifest_sha256"
            ],
        "status": "NO_CONFLICTS",
        "policy": {
            "predictions_visible": False,
            "engine_version_visible": False,
            "auto_resolution_performed": False,
        },
        "passes": {
            "pass_1": {
                "sha256": first["sha256"],
            },
            "pass_2": {
                "sha256": second["sha256"],
            },
        },
        "agreements":
            comparison_result["agreements"],
        "conflicts": [],
    }

    comparison_path = write_json(
        tmp_path / "comparison.json",
        comparison_document,
    )

    adjudication_document = (
        ADJUDICATION.build_document(
            selection_root=selection_root,
            pass_one_path=pass_one_path,
            pass_two_path=pass_two_path,
            comparison_path=comparison_path,
            adjudicator_id="ADJUDICATOR",
            created_at=datetime(
                2026,
                10,
                10,
                12,
                tzinfo=timezone.utc,
            ),
        )
    )

    adjudication_document[
        "status"
    ] = "COMPLETE"
    adjudication_document[
        "completed_at_utc"
    ] = "2026-10-10T13:00:00Z"

    adjudication_path = write_json(
        tmp_path / "adjudication.json",
        adjudication_document,
    )

    return {
        "selection_root": selection_root,
        "protocol_path": protocol_path,
        "pass_one": pass_one_path,
        "pass_two": pass_two_path,
        "comparison": comparison_path,
        "adjudication": adjudication_path,
    }


def run_freezer(
    monkeypatch: pytest.MonkeyPatch,
    *,
    sources: dict[str, Path],
    output_root: Path,
) -> int:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "freezer",
            "--selection-root",
            str(
                sources[
                    "selection_root"
                ]
            ),
            "--pass-one",
            str(sources["pass_one"]),
            "--pass-two",
            str(sources["pass_two"]),
            "--comparison",
            str(sources["comparison"]),
            "--adjudication",
            str(
                sources[
                    "adjudication"
                ]
            ),
            "--output-root",
            str(output_root),
            "--frozen-at",
            "2026-10-11T00:00:00Z",
        ],
    )

    return FREEZER.main()


def test_freezer_creates_self_contained_valid_immutable_package(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    sources = create_sources(tmp_path)
    output_root = (
        tmp_path / "frozen-benchmark"
    )

    assert run_freezer(
        monkeypatch,
        sources=sources,
        output_root=output_root,
    ) == 0

    data_path = (
        output_root
        / FREEZER.DATA_FILENAME
    )
    labels_path = (
        output_root
        / FREEZER.LABELS_FILENAME
    )
    manifest_path = (
        output_root
        / FREEZER.MANIFEST_FILENAME
    )
    receipt_path = (
        output_root
        / FREEZER.RECEIPT_FILENAME
    )

    for path in (
        data_path,
        labels_path,
        manifest_path,
        receipt_path,
    ):
        assert path.exists()

    labels = json.loads(
        labels_path.read_text(
            encoding="utf-8"
        )
    )

    assert labels[
        "label_origin"
    ] == "HUMAN_ADJUDICATED"
    assert labels["status"] == (
        "FROZEN_HUMAN_ADJUDICATED"
    )
    assert len(labels["samples"]) == 2
    assert len(labels["swings"]) == 3

    assert labels["review"][
        "prediction_visibility"
    ] == "HIDDEN_UNTIL_LABEL_FREEZE"

    assert labels["review"][
        "engine_version_visibility"
    ] == "HIDDEN_UNTIL_LABEL_FREEZE"

    issues = validate_annotation_document(
        labels_path
    )

    assert not [
        issue
        for issue in issues
        if issue.severity == "ERROR"
    ]

    manifest = json.loads(
        manifest_path.read_text(
            encoding="utf-8"
        )
    )

    assert manifest["status"] == (
        "FROZEN_UNBLINDED_LABELS_"
        "NOT_EVALUATED"
    )

    assert manifest[
        "contamination_controls"
    ] == {
        "predictions_loaded": False,
        "swing_detector_executed": False,
        "candidate_evaluated": False,
        "baseline_evaluated": False,
    }

    specs = load_manifest(
        manifest_path
    )

    assert len(specs) == 2
    assert all(
        spec.split == "TEST"
        for spec in specs
    )

    label_counts = {
        "XAUUSD_H1_POST_2026H1_001": 2,
        "XAUUSD_H1_POST_2026H1_002": 1,
    }

    for spec in specs:
        assert resolve_data_path(
            spec,
            manifest_path=manifest_path,
        ) == data_path.resolve()

        resolved_labels_path = (
            _labels_path(
                spec,
                manifest_path=(
                    manifest_path
                ),
            )
        )

        assert resolved_labels_path == (
            labels_path.resolve()
        )

        bars = load_real_bars(
            spec,
            manifest_path=manifest_path,
        )

        assert len(bars) == 8

        ground_truth, document = (
            load_labels(
                resolved_labels_path,
                sample_id=spec.sample_id,
            )
        )

        assert document[
            "label_origin"
        ] == "HUMAN_ADJUDICATED"

        assert len(ground_truth) == (
            label_counts[
                spec.sample_id
            ]
        )

    receipt = json.loads(
        receipt_path.read_text(
            encoding="utf-8"
        )
    )

    assert receipt["counts"] == {
        "windows": 2,
        "bars": 16,
        "labels": 3,
        "labels_by_sample": {
            "XAUUSD_H1_POST_2026H1_001": 2,
            "XAUUSD_H1_POST_2026H1_002": 1,
        },
    }

    assert receipt["policy"] == {
        "predictions_loaded": False,
        "swing_detector_executed": False,
        "candidate_evaluated": False,
        "baseline_evaluated": False,
        "evaluation_allowed_after_freeze": True,
    }

    with pytest.raises(
        SystemExit,
        match=(
            "immutable frozen benchmark "
            "already exists"
        ),
    ):
        run_freezer(
            monkeypatch,
            sources=sources,
            output_root=output_root,
        )


def test_freezer_refuses_incomplete_adjudication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    sources = create_sources(tmp_path)

    adjudication = json.loads(
        sources[
            "adjudication"
        ].read_text(encoding="utf-8")
    )

    adjudication["status"] = "DRAFT"
    adjudication[
        "completed_at_utc"
    ] = None

    write_json(
        sources["adjudication"],
        adjudication,
    )

    output_root = (
        tmp_path / "frozen-benchmark"
    )

    with pytest.raises(
        SystemExit,
        match=(
            "adjudication must be COMPLETE"
        ),
    ):
        run_freezer(
            monkeypatch,
            sources=sources,
            output_root=output_root,
        )

    assert not output_root.exists()


def test_freezer_refuses_tampered_frozen_protocol(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    sources = create_sources(tmp_path)

    protocol = json.loads(
        sources[
            "protocol_path"
        ].read_text(encoding="utf-8")
    )

    protocol["candidate"][
        "version"
    ] = "tampered"

    write_json(
        sources["protocol_path"],
        protocol,
    )

    output_root = (
        tmp_path / "frozen-benchmark"
    )

    with pytest.raises(
        SystemExit,
        match=(
            "frozen protocol SHA-256 mismatch"
        ),
    ):
        run_freezer(
            monkeypatch,
            sources=sources,
            output_root=output_root,
        )

    assert not output_root.exists()

"""Regression tests for explicit post-2026H1 adjudication."""

from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


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


ADJUDICATION = load_module(
    ROOT
    / "scripts"
    / "manage_xauusd_h1_post_2026h1_adjudication.py",
    "test_post_2026h1_adjudication_manager",
)

HELPERS = load_module(
    ROOT
    / "tests"
    / "benchmarks"
    / "test_post_2026h1_label_passes.py",
    "test_post_2026h1_adjudication_helpers",
)

PASSES = ADJUDICATION.PASSES


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
) -> dict:
    selection_root = (
        HELPERS.create_selection_root(
            tmp_path
        )
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

    pass_one_document = (
        HELPERS.completed_document(
            selection_root,
            pass_number=1,
            annotator_id="ANNOTATOR_A",
            created_at=first_created,
            completed_at=first_completed,
            labels=[
                HELPERS.label(
                    "P1_AGREE",
                    window_number=1,
                    pivot_index=1,
                    direction="HIGH",
                    tier="MAJOR",
                    scope="EXTERNAL",
                    confirmed_at_index=2,
                ),
                HELPERS.label(
                    "P1_ATTRIBUTE",
                    window_number=1,
                    pivot_index=4,
                    direction="LOW",
                    tier="MINOR",
                    scope="INTERNAL",
                    confirmed_at_index=5,
                ),
                HELPERS.label(
                    "P1_ONLY",
                    window_number=2,
                    pivot_index=5,
                    direction="LOW",
                    tier="MAJOR",
                    scope="EXTERNAL",
                    confirmed_at_index=6,
                ),
            ],
        )
    )

    pass_two_document = (
        HELPERS.completed_document(
            selection_root,
            pass_number=2,
            annotator_id="ANNOTATOR_B",
            created_at=second_created,
            completed_at=second_completed,
            labels=[
                HELPERS.label(
                    "P2_AGREE",
                    window_number=1,
                    pivot_index=1,
                    direction="HIGH",
                    tier="MAJOR",
                    scope="EXTERNAL",
                    confirmed_at_index=2,
                ),
                HELPERS.label(
                    "P2_ATTRIBUTE",
                    window_number=1,
                    pivot_index=4,
                    direction="LOW",
                    tier="MAJOR",
                    scope="INTERNAL",
                    confirmed_at_index=5,
                ),
                HELPERS.label(
                    "P2_ONLY",
                    window_number=2,
                    pivot_index=2,
                    direction="HIGH",
                    tier="MINOR",
                    scope="INTERNAL",
                    confirmed_at_index=3,
                ),
            ],
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

    comparison_document = {
        "schema_version":
            PASSES.COMPARISON_SCHEMA,
        "protocol_id": first[
            "protocol_id"
        ],
        "selection_manifest_sha256":
            first[
                "selection_manifest_sha256"
            ],
        "status": (
            "ADJUDICATION_REQUIRED"
            if comparison_result["conflicts"]
            else "NO_CONFLICTS"
        ),
        "policy": {
            "predictions_visible": False,
            "engine_version_visible": False,
            "auto_resolution_performed":
                False,
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
        "conflicts":
            comparison_result["conflicts"],
    }

    comparison_path = write_json(
        tmp_path / "comparison.json",
        comparison_document,
    )

    return {
        "selection_root": selection_root,
        "pass_one_path": pass_one_path,
        "pass_two_path": pass_two_path,
        "comparison_path": comparison_path,
    }


def build_adjudication(
    sources: dict,
) -> dict:
    return ADJUDICATION.build_document(
        selection_root=sources[
            "selection_root"
        ],
        pass_one_path=sources[
            "pass_one_path"
        ],
        pass_two_path=sources[
            "pass_two_path"
        ],
        comparison_path=sources[
            "comparison_path"
        ],
        adjudicator_id="ADJUDICATOR",
        created_at=datetime(
            2026,
            10,
            10,
            12,
            tzinfo=timezone.utc,
        ),
    )


def validate(
    document: dict,
    sources: dict,
):
    return ADJUDICATION.validate_document(
        document,
        selection_root=sources[
            "selection_root"
        ],
        pass_one_path=sources[
            "pass_one_path"
        ],
        pass_two_path=sources[
            "pass_two_path"
        ],
        comparison_path=sources[
            "comparison_path"
        ],
    )


def complete_document(
    document: dict,
) -> None:
    document["status"] = "COMPLETE"
    document["completed_at_utc"] = (
        "2026-10-10T13:00:00Z"
    )


def conflict_by_type(
    document: dict,
    conflict_type: str,
) -> dict:
    return next(
        conflict
        for conflict in document["conflicts"]
        if conflict["conflict_type"]
        == conflict_type
    )


def test_template_is_blind_and_has_no_automatic_decisions(
    tmp_path: Path,
):
    sources = create_sources(tmp_path)
    document = build_adjudication(
        sources
    )

    assert document["status"] == "DRAFT"
    assert document["blindness"] == {
        "predictions_visible": False,
        "engine_version_visible": False,
    }
    assert document["policy"][
        "auto_resolution_performed"
    ] is False

    assert len(document["agreements"]) == 1
    assert len(document["conflicts"]) == 3

    assert all(
        conflict["decision"] is None
        and conflict["custom_label"]
        is None
        and conflict["notes"] == ""
        for conflict in document["conflicts"]
    )

    result = validate(
        document,
        sources,
    )

    assert result["status"] == "DRAFT"
    assert result["resolved_labels"] == []


def test_complete_adjudication_requires_every_conflict_resolved(
    tmp_path: Path,
):
    sources = create_sources(tmp_path)
    document = build_adjudication(
        sources
    )

    complete_document(document)

    with pytest.raises(
        SystemExit,
        match="unresolved conflicts",
    ):
        validate(
            document,
            sources,
        )


def test_explicit_pass_custom_and_exclude_decisions_validate(
    tmp_path: Path,
):
    sources = create_sources(tmp_path)
    document = build_adjudication(
        sources
    )

    attribute = conflict_by_type(
        document,
        "ATTRIBUTE_CONFLICT",
    )
    attribute["decision"] = "PASS_2"
    attribute["notes"] = (
        "Pass 2 hierarchy classification "
        "is accepted after adjudicator review."
    )

    pass_one_only = conflict_by_type(
        document,
        "PASS_1_ONLY",
    )
    pass_one_only["decision"] = "EXCLUDE"
    pass_one_only["notes"] = (
        "Insufficient confirmation for a "
        "final locked-benchmark label."
    )

    pass_two_only = conflict_by_type(
        document,
        "PASS_2_ONLY",
    )
    pass_two_only["decision"] = "CUSTOM"
    pass_two_only["custom_label"] = {
        **pass_two_only["pass_2"],
        "tier": "MAJOR",
        "scope": "INTERNAL",
        "notes": (
            "Custom semantic classification "
            "selected by adjudicator."
        ),
    }
    pass_two_only["notes"] = (
        "Location accepted; semantic class "
        "was explicitly adjudicated."
    )

    complete_document(document)

    result = validate(
        document,
        sources,
    )

    assert result["status"] == "COMPLETE"
    assert len(
        result["resolved_labels"]
    ) == 3

    identities = {
        (
            label["window_number"],
            label["pivot_index"],
            label["direction"],
            label["tier"],
            label["scope"],
        )
        for label in result[
            "resolved_labels"
        ]
    }

    assert (
        1,
        1,
        "HIGH",
        "MAJOR",
        "EXTERNAL",
    ) in identities

    assert (
        1,
        4,
        "LOW",
        "MAJOR",
        "INTERNAL",
    ) in identities

    assert (
        2,
        2,
        "HIGH",
        "MAJOR",
        "INTERNAL",
    ) in identities


def test_custom_resolution_must_preserve_conflict_identity(
    tmp_path: Path,
):
    sources = create_sources(tmp_path)
    document = build_adjudication(
        sources
    )

    for conflict in document[
        "conflicts"
    ]:
        conflict["decision"] = "EXCLUDE"
        conflict["notes"] = (
            "Explicitly excluded."
        )

    pass_two_only = conflict_by_type(
        document,
        "PASS_2_ONLY",
    )
    pass_two_only["decision"] = "CUSTOM"
    pass_two_only["custom_label"] = {
        **pass_two_only["pass_2"],
        "pivot_index": 3,
    }
    pass_two_only["notes"] = (
        "Attempted custom decision."
    )

    complete_document(document)

    with pytest.raises(
        SystemExit,
        match=(
            "resolved label identity "
            "does not match conflict identity"
        ),
    ):
        validate(
            document,
            sources,
        )


def test_conflict_evidence_is_immutable(
    tmp_path: Path,
):
    sources = create_sources(tmp_path)
    document = build_adjudication(
        sources
    )

    document["conflicts"][0][
        "identity"
    ]["pivot_index"] += 1

    with pytest.raises(
        SystemExit,
        match=(
            "immutable field identity "
            "was changed"
        ),
    ):
        validate(
            document,
            sources,
        )


def test_resolution_requires_non_empty_notes(
    tmp_path: Path,
):
    sources = create_sources(tmp_path)
    document = build_adjudication(
        sources
    )

    for conflict in document[
        "conflicts"
    ]:
        conflict["decision"] = "EXCLUDE"
        conflict["notes"] = (
            "Explicit adjudication."
        )

    document["conflicts"][0][
        "notes"
    ] = ""

    complete_document(document)

    with pytest.raises(
        SystemExit,
        match=(
            "adjudication notes must "
            "be non-empty"
        ),
    ):
        validate(
            document,
            sources,
        )

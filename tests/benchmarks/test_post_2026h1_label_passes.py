"""Regression tests for blind post-2026H1 labeling passes."""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


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


MANAGER = load_script(
    "manage_xauusd_h1_post_2026h1_label_passes.py",
    "test_post_2026h1_label_passes",
)


WINDOW_HEADER = [
    "window_bar_index",
    "global_bar_index",
    "timestamp_utc",
    "open",
    "high",
    "low",
    "close",
    "tick_volume",
    "volume",
    "spread_price",
    "symbol",
    "timeframe",
    "source_snapshot_ids",
]


def sha256(path: Path) -> str:
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


def utc_text(value: datetime) -> str:
    return (
        value.astimezone(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def create_selection_root(
    tmp_path: Path,
    *,
    window_count: int = 2,
    bars_per_window: int = 8,
) -> Path:
    root = tmp_path / "locked-selection"
    root.mkdir()

    base = datetime(
        2026,
        10,
        1,
        tzinfo=timezone.utc,
    )

    windows = []

    for window_number in range(
        1,
        window_count + 1,
    ):
        path = (
            root
            / f"window_{window_number:02d}.csv"
        )

        window_start = (
            base
            + timedelta(
                days=window_number - 1
            )
        )

        rows = []

        for local_index in range(
            bars_per_window
        ):
            timestamp = (
                window_start
                + timedelta(hours=local_index)
            )

            global_index = (
                (window_number - 1)
                * bars_per_window
                + local_index
            )

            base_price = (
                4000.0
                + global_index
            )

            rows.append(
                [
                    local_index,
                    global_index,
                    utc_text(timestamp),
                    f"{base_price:.2f}",
                    f"{base_price + 2:.2f}",
                    f"{base_price - 2:.2f}",
                    f"{base_price + 1:.2f}",
                    1000 + global_index,
                    0,
                    "0.29",
                    "XAUUSD.vx",
                    "PERIOD_H1",
                    "TEST_SNAPSHOT",
                ]
            )

        with path.open(
            "w",
            encoding="utf-8",
            newline="",
        ) as handle:
            writer = csv.writer(
                handle,
                lineterminator="\n",
            )
            writer.writerow(WINDOW_HEADER)
            writer.writerows(rows)

        windows.append(
            {
                "window_number": window_number,
                "bucket_start_index": (
                    (window_number - 1)
                    * bars_per_window
                ),
                "bucket_end_index_exclusive": (
                    window_number
                    * bars_per_window
                ),
                "bucket_bars": bars_per_window,
                "start_index": (
                    (window_number - 1)
                    * bars_per_window
                ),
                "end_index_exclusive": (
                    window_number
                    * bars_per_window
                ),
                "bars": bars_per_window,
                "first_utc": rows[0][2],
                "last_utc": rows[-1][2],
                "path": path.name,
                "sha256": sha256(path),
            }
        )

    manifest = {
        "protocol_id":
            "XAUUSD_H1_POST_2026H1_LOCKED_TEST",
        "status": (
            "WINDOWS_SELECTED_UNLABELED_"
            "NOT_EVALUATED"
        ),
        "policy": {
            "labels_loaded": False,
            "predictions_loaded": False,
            "swing_engine_imported": False,
            "swing_engine_executed": False,
            "selection_uses_prices": False,
            "selection_uses_predictions": False,
            "selection_uses_chronology_and_indices_only":
                True,
        },
        "selection_parameters": {
            "leading_guard_bars": 48,
            "trailing_guard_bars": 48,
            "bucket_count": window_count,
            "window_bars": bars_per_window,
        },
        "windows": windows,
        "contamination_controls": {
            "labels_exist": False,
            "predictions_exist": False,
            "swing_engine_executed": False,
            "candidate_evaluated": False,
            "baseline_evaluated": False,
        },
    }

    (
        root / "selection_manifest.json"
    ).write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )

    return root


def label(
    label_id: str,
    *,
    window_number: int,
    pivot_index: int,
    direction: str,
    tier: str,
    scope: str,
    confirmed_at_index: int,
) -> dict:
    return {
        "label_id": label_id,
        "window_number": window_number,
        "pivot_index": pivot_index,
        "direction": direction,
        "tier": tier,
        "scope": scope,
        "confirmed_at_index":
            confirmed_at_index,
        "notes": "",
    }


def completed_document(
    selection_root: Path,
    *,
    pass_number: int,
    annotator_id: str,
    created_at: datetime,
    completed_at: datetime,
    labels: list[dict],
) -> dict:
    document = MANAGER.build_pass_document(
        selection_root=selection_root,
        pass_number=pass_number,
        annotator_id=annotator_id,
        created_at=created_at,
    )

    document["status"] = "COMPLETE"
    document["completed_at_utc"] = (
        utc_text(completed_at)
    )
    document["labels"] = labels

    return document


def test_prepare_pass_is_empty_and_fully_blinded(
    tmp_path: Path,
):
    selection_root = create_selection_root(
        tmp_path
    )

    created_at = datetime(
        2026,
        10,
        2,
        12,
        tzinfo=timezone.utc,
    )

    document = MANAGER.build_pass_document(
        selection_root=selection_root,
        pass_number=1,
        annotator_id="ANNOTATOR_A",
        created_at=created_at,
    )

    assert document["schema_version"] == (
        MANAGER.PASS_SCHEMA
    )
    assert document["status"] == "DRAFT"
    assert document["labels"] == []
    assert document["completed_at_utc"] is None
    assert document["created_at_utc"] == (
        "2026-10-02T12:00:00Z"
    )
    assert len(document["windows"]) == 2

    assert document["blindness"] == {
        "predictions_visible": False,
        "engine_version_visible": False,
        "prior_pass_visible": False,
        "comparison_visible": False,
        "adjudication_visible": False,
    }


def test_completed_pass_validates_and_rejects_broken_blindness(
    tmp_path: Path,
):
    selection_root = create_selection_root(
        tmp_path
    )

    created = datetime(
        2026,
        10,
        2,
        12,
        tzinfo=timezone.utc,
    )

    completed = created + timedelta(hours=2)

    document = completed_document(
        selection_root,
        pass_number=1,
        annotator_id="ANNOTATOR_A",
        created_at=created,
        completed_at=completed,
        labels=[
            label(
                "P1_HIGH",
                window_number=1,
                pivot_index=1,
                direction="HIGH",
                tier="MAJOR",
                scope="EXTERNAL",
                confirmed_at_index=2,
            ),
            label(
                "P1_LOW",
                window_number=1,
                pivot_index=4,
                direction="LOW",
                tier="MINOR",
                scope="INTERNAL",
                confirmed_at_index=5,
            ),
        ],
    )

    validated = (
        MANAGER.validate_pass_document(
            document,
            selection_root=selection_root,
        )
    )

    assert validated["pass_number"] == 1
    assert validated["status"] == "COMPLETE"
    assert len(validated["labels"]) == 2

    document["blindness"][
        "predictions_visible"
    ] = True

    with pytest.raises(
        SystemExit,
        match="predictions_visible",
    ):
        MANAGER.validate_pass_document(
            document,
            selection_root=selection_root,
        )


def test_validation_rejects_non_alternating_labels(
    tmp_path: Path,
):
    selection_root = create_selection_root(
        tmp_path
    )

    created = datetime(
        2026,
        10,
        2,
        12,
        tzinfo=timezone.utc,
    )

    document = completed_document(
        selection_root,
        pass_number=1,
        annotator_id="ANNOTATOR_A",
        created_at=created,
        completed_at=(
            created + timedelta(hours=1)
        ),
        labels=[
            label(
                "HIGH_1",
                window_number=1,
                pivot_index=1,
                direction="HIGH",
                tier="MAJOR",
                scope="EXTERNAL",
                confirmed_at_index=2,
            ),
            label(
                "HIGH_2",
                window_number=1,
                pivot_index=4,
                direction="HIGH",
                tier="MINOR",
                scope="INTERNAL",
                confirmed_at_index=5,
            ),
        ],
    )

    with pytest.raises(
        SystemExit,
        match="labels must alternate direction",
    ):
        MANAGER.validate_pass_document(
            document,
            selection_root=selection_root,
        )


def test_second_pass_delay_is_enforced(
    tmp_path: Path,
):
    selection_root = create_selection_root(
        tmp_path
    )

    created = datetime(
        2026,
        10,
        2,
        12,
        tzinfo=timezone.utc,
    )

    completed = (
        created + timedelta(hours=1)
    )

    prior_document = completed_document(
        selection_root,
        pass_number=1,
        annotator_id="ANNOTATOR_A",
        created_at=created,
        completed_at=completed,
        labels=[],
    )

    prior = MANAGER.validate_pass_document(
        prior_document,
        selection_root=selection_root,
    )

    with pytest.raises(
        SystemExit,
        match="pass 2 cannot begin before",
    ):
        MANAGER.ensure_second_pass_delay(
            prior=prior,
            created_at=(
                completed
                + timedelta(
                    days=2,
                    hours=23,
                )
            ),
            minimum_days=3,
        )

    MANAGER.ensure_second_pass_delay(
        prior=prior,
        created_at=(
            completed + timedelta(days=3)
        ),
        minimum_days=3,
    )


def test_compare_reports_agreements_and_all_conflict_types(
    tmp_path: Path,
):
    selection_root = create_selection_root(
        tmp_path
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

    first_document = completed_document(
        selection_root,
        pass_number=1,
        annotator_id="ANNOTATOR_A",
        created_at=first_created,
        completed_at=first_completed,
        labels=[
            label(
                "P1_AGREE",
                window_number=1,
                pivot_index=1,
                direction="HIGH",
                tier="MAJOR",
                scope="EXTERNAL",
                confirmed_at_index=2,
            ),
            label(
                "P1_ATTR",
                window_number=1,
                pivot_index=4,
                direction="LOW",
                tier="MINOR",
                scope="INTERNAL",
                confirmed_at_index=5,
            ),
            label(
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

    second_document = completed_document(
        selection_root,
        pass_number=2,
        annotator_id="ANNOTATOR_B",
        created_at=second_created,
        completed_at=second_completed,
        labels=[
            label(
                "P2_AGREE",
                window_number=1,
                pivot_index=1,
                direction="HIGH",
                tier="MAJOR",
                scope="EXTERNAL",
                confirmed_at_index=2,
            ),
            label(
                "P2_ATTR",
                window_number=1,
                pivot_index=4,
                direction="LOW",
                tier="MAJOR",
                scope="INTERNAL",
                confirmed_at_index=5,
            ),
            label(
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

    first = MANAGER.validate_pass_document(
        first_document,
        selection_root=selection_root,
    )

    second = MANAGER.validate_pass_document(
        second_document,
        selection_root=selection_root,
    )

    result = MANAGER.compare_passes(
        first,
        second,
        minimum_days=3,
    )

    assert result["separation_hours"] == 72.0
    assert len(result["agreements"]) == 1
    assert len(result["conflicts"]) == 3

    assert {
        conflict["conflict_type"]
        for conflict in result["conflicts"]
    } == {
        "ATTRIBUTE_CONFLICT",
        "PASS_1_ONLY",
        "PASS_2_ONLY",
    }

    attribute_conflict = next(
        conflict
        for conflict in result["conflicts"]
        if conflict["conflict_type"]
        == "ATTRIBUTE_CONFLICT"
    )

    assert attribute_conflict[
        "differences"
    ] == {
        "tier": {
            "pass_1": "MINOR",
            "pass_2": "MAJOR",
        }
    }


def test_contaminated_selection_is_rejected(
    tmp_path: Path,
):
    selection_root = create_selection_root(
        tmp_path
    )

    manifest_path = (
        selection_root
        / "selection_manifest.json"
    )

    manifest = json.loads(
        manifest_path.read_text(
            encoding="utf-8"
        )
    )

    manifest[
        "contamination_controls"
    ]["predictions_exist"] = True

    manifest_path.write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        SystemExit,
        match="predictions_exist",
    ):
        MANAGER.build_pass_document(
            selection_root=selection_root,
            pass_number=1,
            annotator_id="ANNOTATOR_A",
            created_at=datetime(
                2026,
                10,
                2,
                tzinfo=timezone.utc,
            ),
        )

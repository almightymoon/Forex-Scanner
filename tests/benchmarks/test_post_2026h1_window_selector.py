"""Regression tests for deterministic post-2026H1 window selection."""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import sys
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


SELECTOR = load_script(
    "select_xauusd_h1_post_2026h1_locked_windows.py",
    "test_post_2026h1_window_selector",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


def protocol_payload(
    *,
    minimum_bars: int,
    required_end: datetime,
    protocol_id: str = "TEST_LOCKED_PROTOCOL",
) -> dict:
    return {
        "protocol_id": protocol_id,
        "accrual_requirements": {
            "minimum_unique_h1_bars": minimum_bars,
            "not_before_utc": (
                required_end.isoformat()
                .replace("+00:00", "Z")
            ),
        },
        "window_selection": {
            "performed_only_after_accrual_requirements_pass":
                True,
            "selection_uses_prices_or_predictions":
                False,
            "leading_guard_bars": 48,
            "trailing_guard_bars": 48,
            "bucket_count": 6,
            "window_bars": 192,
            "algorithm": [
                "chronology only"
            ],
        },
    }


def synthetic_selection_bars(
    count: int,
) -> list[dict]:
    start = datetime(
        2026,
        7,
        1,
        tzinfo=timezone.utc,
    )

    return [
        {
            "timestamp_utc": (
                start + timedelta(hours=index)
            )
        }
        for index in range(count)
    ]


def write_snapshot(
    quarantine_root: Path,
    *,
    count: int,
    start: datetime,
    snapshot_stamp: str = "20261001T000000Z",
) -> Path:
    snapshot_root = (
        quarantine_root / snapshot_stamp
    )
    snapshot_root.mkdir(
        parents=True,
        exist_ok=False,
    )

    raw = snapshot_root / "XAUUSD_H1_raw.csv"
    metadata = (
        snapshot_root
        / "XAUUSD_H1_raw.meta.csv"
    )
    audit = (
        snapshot_root
        / "acquisition_audit.json"
    )
    manifest = (
        snapshot_root
        / "snapshot_manifest.json"
    )

    with raw.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.writer(
            handle,
            lineterminator="\r\n",
        )

        writer.writerow(
            [
                "timestamp_server",
                "timestamp_epoch",
                "open",
                "high",
                "low",
                "close",
                "tick_volume",
                "volume",
                "spread_price",
                "symbol",
                "timeframe",
            ]
        )

        for index in range(count):
            timestamp = (
                start + timedelta(hours=index)
            )

            base = 4000.0 + index / 100.0
            open_price = base
            close = base + 0.25
            high = base + 1.00
            low = base - 1.00

            writer.writerow(
                [
                    timestamp.strftime(
                        "%Y.%m.%d %H:%M:%S"
                    ),
                    int(timestamp.timestamp()),
                    f"{open_price:.2f}",
                    f"{high:.2f}",
                    f"{low:.2f}",
                    f"{close:.2f}",
                    1000 + index,
                    0,
                    "0.29",
                    "XAUUSD.vx",
                    "PERIOD_H1",
                ]
            )

    metadata_rows = {
        "dataset_role":
            "UNLABELED_QUARANTINED_RAW_CANDLES",
        "symbol": "XAUUSD.vx",
        "timeframe": "PERIOD_H1",
        "requested_start_server":
            start.strftime("%Y.%m.%d %H:%M:%S"),
        "first_bar_server":
            start.strftime("%Y.%m.%d %H:%M:%S"),
        "first_bar_epoch":
            str(int(start.timestamp())),
        "last_closed_bar_server": (
            start
            + timedelta(hours=count - 1)
        ).strftime("%Y.%m.%d %H:%M:%S"),
        "last_closed_bar_epoch": str(
            int(
                (
                    start
                    + timedelta(hours=count - 1)
                ).timestamp()
            )
        ),
        "rows": str(count),
        "raw_file": raw.name,
        "account_server": "Test-Server",
        "terminal_company": "Test",
        "terminal_name": "MetaTrader 5",
        "exported_at_server":
            "2026.10.01 00:00:00",
        "exported_at_gmt":
            "2026.10.01 00:00:00",
        "server_minus_gmt_seconds_at_export":
            "0",
        "contains_labels": "false",
        "contains_predictions": "false",
        "engine_version_evaluated": "none",
    }

    with metadata.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.writer(
            handle,
            lineterminator="\r\n",
        )
        writer.writerow(["key", "value"])
        writer.writerows(
            metadata_rows.items()
        )

    audit_payload = {
        "status": "PASS",
        "policy": {
            "labels_loaded": False,
            "predictions_loaded": False,
            "swing_engine_executed": False,
        },
    }

    audit.write_text(
        json.dumps(
            audit_payload,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    manifest_payload = {
        "snapshot_id": (
            "XAUUSD_H1_POST_2026H1_"
            f"{snapshot_stamp}"
        ),
        "status": (
            "QUARANTINED_UNLABELED_"
            "ACCRUAL_TRANCHE"
        ),
        "files": {
            "raw": {
                "path": raw.name,
                "sha256": sha256(raw),
            },
            "metadata": {
                "path": metadata.name,
                "sha256": sha256(metadata),
            },
            "audit": {
                "path": audit.name,
                "sha256": sha256(audit),
            },
        },
        "contamination_controls": {
            "labels_exist": False,
            "predictions_exist": False,
            "swing_engine_executed": False,
            "v2_3_evaluated": False,
        },
    }

    manifest.write_text(
        json.dumps(
            manifest_payload,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    return snapshot_root


def run_selector(
    monkeypatch: pytest.MonkeyPatch,
    *,
    protocol_path: Path,
    quarantine_root: Path,
    output_parent: Path,
) -> int:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "selector",
            "--protocol",
            str(protocol_path),
            "--quarantine-root",
            str(quarantine_root),
            "--output-parent",
            str(output_parent),
        ],
    )

    return SELECTOR.main()


def test_window_selection_is_deterministic_and_non_overlapping():
    bars = synthetic_selection_bars(
        1400
    )

    protocol = protocol_payload(
        minimum_bars=1400,
        required_end=bars[-1][
            "timestamp_utc"
        ],
    )

    first = SELECTOR.select_windows(
        bars,
        protocol,
    )

    second = SELECTOR.select_windows(
        bars,
        protocol,
    )

    assert first == second
    assert len(first) == 6

    assert [
        row["start_index"]
        for row in first
    ] == [
        60,
        277,
        495,
        712,
        929,
        1147,
    ]

    assert all(
        row["bars"] == 192
        for row in first
    )

    assert all(
        left["end_index_exclusive"]
        <= right["start_index"]
        for left, right in zip(
            first,
            first[1:],
        )
    )


def test_window_selection_refuses_undersized_buckets():
    bars = synthetic_selection_bars(
        1000
    )

    protocol = protocol_payload(
        minimum_bars=1000,
        required_end=bars[-1][
            "timestamp_utc"
        ],
    )

    with pytest.raises(
        SystemExit,
        match="contains only",
    ):
        SELECTOR.select_windows(
            bars,
            protocol,
        )


def test_main_refuses_before_frozen_accrual_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    quarantine_root = (
        tmp_path / "quarantine"
    )

    start = datetime(
        2026,
        7,
        1,
        tzinfo=timezone.utc,
    )

    write_snapshot(
        quarantine_root,
        count=20,
        start=start,
    )

    protocol_path = (
        tmp_path / "protocol.json"
    )

    protocol_path.write_text(
        json.dumps(
            protocol_payload(
                minimum_bars=30,
                required_end=(
                    start
                    + timedelta(hours=29)
                ),
            )
        ),
        encoding="utf-8",
    )

    output_parent = (
        tmp_path / "locked"
    )

    with pytest.raises(
        SystemExit,
        match=(
            "frozen accrual requirements "
            "have not all passed"
        ),
    ):
        run_selector(
            monkeypatch,
            protocol_path=protocol_path,
            quarantine_root=quarantine_root,
            output_parent=output_parent,
        )

    assert not output_parent.exists()


def test_main_writes_one_immutable_unlabeled_window_set(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    quarantine_root = (
        tmp_path / "quarantine"
    )

    start = datetime(
        2026,
        7,
        1,
        tzinfo=timezone.utc,
    )

    count = 1400

    write_snapshot(
        quarantine_root,
        count=count,
        start=start,
    )

    last = (
        start
        + timedelta(hours=count - 1)
    )

    protocol_id = (
        "TEST_LOCKED_PROTOCOL"
    )

    protocol_path = (
        tmp_path / "protocol.json"
    )

    protocol_path.write_text(
        json.dumps(
            protocol_payload(
                minimum_bars=count,
                required_end=last,
                protocol_id=protocol_id,
            )
        ),
        encoding="utf-8",
    )

    output_parent = (
        tmp_path / "locked"
    )

    assert run_selector(
        monkeypatch,
        protocol_path=protocol_path,
        quarantine_root=quarantine_root,
        output_parent=output_parent,
    ) == 0

    output_root = (
        output_parent / protocol_id
    )

    manifest_path = (
        output_root
        / "selection_manifest.json"
    )

    assert manifest_path.exists()

    manifest = json.loads(
        manifest_path.read_text(
            encoding="utf-8"
        )
    )

    assert manifest["status"] == (
        "WINDOWS_SELECTED_UNLABELED_"
        "NOT_EVALUATED"
    )

    assert manifest["policy"] == {
        "labels_loaded": False,
        "predictions_loaded": False,
        "swing_engine_imported": False,
        "swing_engine_executed": False,
        "selection_uses_prices": False,
        "selection_uses_predictions": False,
        "selection_uses_chronology_and_indices_only":
            True,
    }

    assert manifest[
        "contamination_controls"
    ] == {
        "labels_exist": False,
        "predictions_exist": False,
        "swing_engine_executed": False,
        "candidate_evaluated": False,
        "baseline_evaluated": False,
    }

    assert manifest["combined_input"][
        "unique_normalized_bars"
    ] == count

    assert len(manifest["windows"]) == 6

    for window in manifest["windows"]:
        path = (
            output_root / window["path"]
        )

        assert path.exists()
        assert sha256(path) == (
            window["sha256"]
        )

        with path.open(
            "r",
            encoding="utf-8",
            newline="",
        ) as handle:
            rows = list(
                csv.DictReader(handle)
            )

        assert len(rows) == 192
        assert [
            int(row["window_bar_index"])
            for row in rows
        ] == list(range(192))

    with pytest.raises(
        SystemExit,
        match=(
            "immutable locked-window set "
            "already exists"
        ),
    ):
        run_selector(
            monkeypatch,
            protocol_path=protocol_path,
            quarantine_root=quarantine_root,
            output_parent=output_parent,
        )

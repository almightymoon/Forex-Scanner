"""Regression tests for the post-2026H1 quarantine toolchain."""

from __future__ import annotations

import csv
import importlib.util
import json
import sys
from datetime import datetime, timezone
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


INGESTER = load_script(
    "ingest_xauusd_h1_post_2026h1_quarantine.py",
    "test_post_2026h1_ingester",
)

STATUS = load_script(
    "status_xauusd_h1_post_2026h1_accrual.py",
    "test_post_2026h1_status",
)


HEADER = [
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


def epoch_for_server_clock(
    value: datetime,
) -> int:
    return int(
        value.replace(
            tzinfo=timezone.utc
        ).timestamp()
    )


def candle_row(
    *,
    server_time: datetime,
    open_price: str = "4019.18",
    high: str = "4019.32",
    low: str = "4010.66",
    close: str = "4013.03",
) -> list[str]:
    return [
        server_time.strftime(
            "%Y.%m.%d %H:%M:%S"
        ),
        str(epoch_for_server_clock(server_time)),
        open_price,
        high,
        low,
        close,
        "7819",
        "0",
        "0.29",
        "XAUUSD.vx",
        "PERIOD_H1",
    ]


def write_raw(
    path: Path,
    rows: list[list[str]],
) -> None:
    with path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.writer(
            handle,
            lineterminator="\r\n",
        )
        writer.writerow(HEADER)
        writer.writerows(rows)


def valid_metadata(
    *,
    rows: int,
    exported_at_gmt: str = "2026.07.18 20:38:08",
) -> dict[str, str]:
    return {
        "dataset_role":
            "UNLABELED_QUARANTINED_RAW_CANDLES",
        "symbol": "XAUUSD.vx",
        "timeframe": "PERIOD_H1",
        "requested_start_server":
            "2026.07.01 00:00:00",
        "first_bar_server":
            "2026.07.01 01:00:00",
        "first_bar_epoch": "1782867600",
        "last_closed_bar_server":
            "2026.07.01 01:00:00",
        "last_closed_bar_epoch": "1782867600",
        "rows": str(rows),
        "raw_file": "incoming.csv",
        "account_server": "Test-Server",
        "terminal_company": "Test",
        "terminal_name": "MetaTrader 5",
        "exported_at_server":
            "2026.07.18 23:38:08",
        "exported_at_gmt": exported_at_gmt,
        "server_minus_gmt_seconds_at_export":
            "10800",
        "contains_labels": "false",
        "contains_predictions": "false",
        "engine_version_evaluated": "none",
    }


def write_metadata(
    path: Path,
    metadata: dict[str, str],
) -> None:
    with path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.writer(
            handle,
            lineterminator="\r\n",
        )
        writer.writerow(["key", "value"])
        writer.writerows(metadata.items())


def test_export_stamp_is_utc_and_deterministic():
    exported = INGESTER.parse_exported_at_gmt(
        "2026.07.18 20:38:08"
    )

    assert INGESTER.snapshot_stamp(exported) == (
        "20260718T203808Z"
    )


def test_metadata_policy_rejects_contamination():
    metadata = valid_metadata(rows=1)
    INGESTER.require_metadata(metadata)

    contaminated = {
        **metadata,
        "contains_predictions": "true",
    }

    with pytest.raises(
        SystemExit,
        match="metadata policy failed",
    ):
        INGESTER.require_metadata(contaminated)


def test_load_candles_normalizes_server_clock_and_counts_duplicates(
    tmp_path: Path,
):
    raw = tmp_path / "raw.csv"
    metadata = valid_metadata(rows=2)

    server_time = datetime(
        2026,
        7,
        1,
        1,
        0,
        0,
    )

    row = candle_row(
        server_time=server_time
    )

    write_raw(raw, [row, row])

    candles, row_count, duplicates = (
        INGESTER.load_candles(
            raw,
            metadata,
        )
    )

    assert row_count == 2
    assert duplicates == 1
    assert len(candles) == 1

    expected_utc = datetime(
        2026,
        6,
        30,
        22,
        0,
        0,
        tzinfo=timezone.utc,
    )

    assert list(candles) == [expected_utc]


def test_load_candles_rejects_conflicting_duplicate_ohlc(
    tmp_path: Path,
):
    raw = tmp_path / "raw.csv"
    metadata = valid_metadata(rows=2)

    server_time = datetime(
        2026,
        7,
        1,
        1,
        0,
        0,
    )

    write_raw(
        raw,
        [
            candle_row(
                server_time=server_time
            ),
            candle_row(
                server_time=server_time,
                close="4014.00",
            ),
        ],
    )

    with pytest.raises(
        SystemExit,
        match="conflicting duplicate OHLC",
    ):
        INGESTER.load_candles(
            raw,
            metadata,
        )


def test_ingestion_is_immutable_byte_preserving_and_status_visible(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    source_raw = tmp_path / "incoming.csv"
    source_metadata = tmp_path / "incoming.meta.csv"

    server_time = datetime(
        2026,
        7,
        1,
        1,
        0,
        0,
    )

    write_raw(
        source_raw,
        [
            candle_row(
                server_time=server_time
            )
        ],
    )

    write_metadata(
        source_metadata,
        valid_metadata(rows=1),
    )

    original_raw_bytes = source_raw.read_bytes()
    original_metadata_bytes = (
        source_metadata.read_bytes()
    )

    quarantine_root = (
        tmp_path / "quarantine"
    )

    monkeypatch.setattr(
        INGESTER,
        "QUARANTINE_ROOT",
        quarantine_root,
    )

    def fake_auditor(
        raw: Path,
        metadata: Path,
        output: Path,
    ) -> dict:
        receipt = {
            "status": "PASS",
            "coverage": {
                "rows": 1,
                "historical_end_utc":
                    "2026-06-30T20:00:00+00:00",
                "first_new_utc":
                    "2026-06-30T22:00:00+00:00",
                "last_new_utc":
                    "2026-06-30T22:00:00+00:00",
                "initial_gap_hours": 2.0,
            },
        }

        output.write_text(
            json.dumps(receipt, indent=2) + "\n",
            encoding="utf-8",
        )
        return receipt

    monkeypatch.setattr(
        INGESTER,
        "run_auditor",
        fake_auditor,
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ingester",
            "--raw",
            str(source_raw),
            "--metadata",
            str(source_metadata),
        ],
    )

    assert INGESTER.main() == 0

    snapshot = (
        quarantine_root
        / "20260718T203808Z"
    )

    frozen_raw = (
        snapshot / "XAUUSD_H1_raw.csv"
    )
    frozen_metadata = (
        snapshot
        / "XAUUSD_H1_raw.meta.csv"
    )

    assert frozen_raw.read_bytes() == (
        original_raw_bytes
    )
    assert frozen_metadata.read_bytes() == (
        original_metadata_bytes
    )

    manifest = json.loads(
        (
            snapshot
            / "snapshot_manifest.json"
        ).read_text(encoding="utf-8")
    )

    assert (
        manifest["ingestion"]["new_unique_bars"]
        == 1
    )
    assert manifest[
        "contamination_controls"
    ] == {
        "labels_exist": False,
        "predictions_exist": False,
        "swing_engine_executed": False,
        "v2_3_evaluated": False,
    }

    with pytest.raises(
        SystemExit,
        match="immutable snapshot already exists",
    ):
        INGESTER.main()

    protocol_path = tmp_path / "protocol.json"
    status_output = tmp_path / "status.json"

    protocol_path.write_text(
        json.dumps(
            {
                "protocol_id": "TEST_PROTOCOL",
                "accrual_requirements": {
                    "minimum_unique_h1_bars": 1,
                    "not_before_utc":
                        "2026-06-30T22:00:00Z",
                },
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        STATUS,
        "QUARANTINE_ROOT",
        quarantine_root,
    )
    monkeypatch.setattr(
        STATUS,
        "PROTOCOL_PATH",
        protocol_path,
    )
    monkeypatch.setattr(
        STATUS,
        "OUTPUT",
        status_output,
    )

    assert STATUS.main() == 0

    status = json.loads(
        status_output.read_text(
            encoding="utf-8"
        )
    )

    assert status["status"] == (
        "READY_FOR_DETERMINISTIC_WINDOW_SELECTION"
    )
    assert status["coverage"][
        "unique_normalized_h1_bars"
    ] == 1
    assert status["gates"][
        "all_requirements_passed"
    ] is True
    assert status["errors"] == []

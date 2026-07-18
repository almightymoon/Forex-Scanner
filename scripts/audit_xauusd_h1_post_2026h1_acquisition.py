#!/usr/bin/env python3
"""Audit a quarantined post-2026H1 XAUUSD H1 candle acquisition.

Loads no labels, predictions, or swing-engine code.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

DEFAULT_HISTORICAL = (
    ROOT
    / "benchmarks"
    / "data"
    / "real"
    / "XAUUSD"
    / "H1_2026H1"
    / "XAUUSD_H1_2026H1.real.csv.gz"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def parse_historical_utc(value: str) -> datetime:
    text = value.strip()

    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    parsed = datetime.fromisoformat(text)

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument(
        "--raw",
        type=Path,
        required=True,
        help="Raw MT5 candle CSV.",
    )
    parser.add_argument(
        "--metadata",
        type=Path,
        required=True,
        help="MT5 acquisition metadata CSV.",
    )
    parser.add_argument(
        "--historical",
        type=Path,
        default=DEFAULT_HISTORICAL,
        help="Historical 2026H1 candle file used only for overlap checks.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="JSON audit receipt destination.",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    raw = args.raw.resolve()
    metadata_path = args.metadata.resolve()
    historical = args.historical.resolve()
    output = args.output.resolve()

    for path in (
        raw,
        metadata_path,
        historical,
    ):
        if not path.exists():
            raise SystemExit(
                f"Missing required file: {path}"
            )

    with metadata_path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        metadata = dict(csv.reader(handle))

    with raw.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        rows = list(csv.DictReader(handle))

    errors: list[str] = []

    if not rows:
        raise SystemExit(
            "Raw acquisition contains no candle rows."
        )

    required_metadata = {
        "dataset_role":
            "UNLABELED_QUARANTINED_RAW_CANDLES",
        "timeframe": "PERIOD_H1",
        "contains_labels": "false",
        "contains_predictions": "false",
        "engine_version_evaluated": "none",
    }

    for key, expected in required_metadata.items():
        actual = metadata.get(key)

        if actual != expected:
            errors.append(
                f"metadata {key!r}: expected "
                f"{expected!r}, got {actual!r}"
            )

    try:
        offset_seconds = int(
            metadata[
                "server_minus_gmt_seconds_at_export"
            ]
        )
    except (KeyError, ValueError):
        offset_seconds = 0
        errors.append(
            "invalid server_minus_gmt_seconds_at_export"
        )

    try:
        expected_rows = int(metadata["rows"])
    except (KeyError, ValueError):
        expected_rows = -1
        errors.append("metadata rows is invalid")

    if expected_rows != len(rows):
        errors.append(
            f"metadata rows={expected_rows}, "
            f"raw rows={len(rows)}"
        )

    normalized_utc: list[datetime] = []

    source_clock_mismatches = 0
    ohlc_errors = 0
    identity_errors = 0

    for line_number, row in enumerate(
        rows,
        start=2,
    ):
        try:
            source_numeric_clock = (
                datetime.fromtimestamp(
                    int(row["timestamp_epoch"]),
                    tz=timezone.utc,
                ).replace(tzinfo=None)
            )

            source_server_clock = datetime.strptime(
                row["timestamp_server"],
                "%Y.%m.%d %H:%M:%S",
            )

            # This MT5 export encodes broker-server wall-clock time in
            # both fields. Normalize to UTC with the recorded offset.
            utc_time = (
                source_numeric_clock
                - timedelta(seconds=offset_seconds)
            ).replace(tzinfo=timezone.utc)

            if (
                source_numeric_clock
                != source_server_clock
            ):
                source_clock_mismatches += 1

            open_price = float(row["open"])
            high = float(row["high"])
            low = float(row["low"])
            close = float(row["close"])
            tick_volume = int(row["tick_volume"])
            real_volume = int(row["volume"])
            spread = float(row["spread_price"])

            if not (
                high >= max(open_price, close)
                and low <= min(open_price, close)
                and high >= low
                and min(
                    open_price,
                    high,
                    low,
                    close,
                ) > 0
                and tick_volume >= 0
                and real_volume >= 0
                and spread >= 0
            ):
                ohlc_errors += 1

            if (
                row["symbol"] != metadata.get("symbol")
                or row["timeframe"] != "PERIOD_H1"
            ):
                identity_errors += 1

            normalized_utc.append(utc_time)

        except Exception as exc:
            errors.append(
                f"row {line_number} parse failure: {exc}"
            )

    if source_clock_mismatches:
        errors.append(
            f"{source_clock_mismatches} source-clock mismatches"
        )

    if ohlc_errors:
        errors.append(
            f"{ohlc_errors} OHLC or volume violations"
        )

    if identity_errors:
        errors.append(
            f"{identity_errors} symbol/timeframe violations"
        )

    duplicate_timestamps = (
        len(normalized_utc)
        - len(set(normalized_utc))
    )

    if duplicate_timestamps:
        errors.append(
            f"{duplicate_timestamps} duplicate timestamps"
        )

    if normalized_utc != sorted(normalized_utc):
        errors.append(
            "normalized candles are not chronological"
        )

    interval_seconds = [
        int((right - left).total_seconds())
        for left, right in zip(
            normalized_utc,
            normalized_utc[1:],
        )
    ]

    invalid_intervals = [
        interval
        for interval in interval_seconds
        if interval <= 0
        or interval % 3600 != 0
    ]

    if invalid_intervals:
        errors.append(
            f"{len(invalid_intervals)} intervals are not "
            "positive whole hours"
        )

    multi_hour_gaps = [
        interval // 3600
        for interval in interval_seconds
        if interval > 3600
    ]

    historical_times: list[datetime] = []

    with gzip.open(
        historical,
        "rt",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        for row in csv.DictReader(handle):
            historical_times.append(
                parse_historical_utc(
                    row["timestamp_utc"]
                )
            )

    historical_end = max(historical_times)
    overlap = (
        set(historical_times)
        & set(normalized_utc)
    )

    if overlap:
        errors.append(
            f"{len(overlap)} timestamps overlap "
            "historical 2026H1 data"
        )

    first_utc = min(normalized_utc)
    last_utc = max(normalized_utc)

    if first_utc <= historical_end:
        errors.append(
            "new acquisition does not start strictly "
            "after historical data"
        )

    initial_gap_hours = (
        first_utc - historical_end
    ).total_seconds() / 3600

    payload = {
        "audit":
            "XAUUSD_H1_POST_2026H1_ACQUISITION_INTEGRITY",
        "generated_at_utc": datetime.now(
            timezone.utc
        ).isoformat(timespec="seconds"),
        "status": "PASS" if not errors else "FAIL",
        "policy": {
            "labels_loaded": False,
            "predictions_loaded": False,
            "swing_engine_executed": False,
            "data_role":
                "UNLABELED_QUARANTINED_RAW_CANDLES",
        },
        "timestamp_model": {
            "source_epoch_semantics":
                "broker_server_wall_clock",
            "server_minus_gmt_seconds":
                offset_seconds,
            "utc_conversion":
                "source_clock_minus_server_offset",
        },
        "files": {
            "raw": display_path(raw),
            "metadata": display_path(metadata_path),
            "historical_comparison":
                display_path(historical),
            "raw_sha256": sha256(raw),
            "metadata_sha256":
                sha256(metadata_path),
        },
        "coverage": {
            "rows": len(rows),
            "historical_end_utc":
                historical_end.isoformat(),
            "first_new_utc":
                first_utc.isoformat(),
            "last_new_utc":
                last_utc.isoformat(),
            "initial_gap_hours":
                initial_gap_hours,
        },
        "integrity": {
            "duplicate_timestamps":
                duplicate_timestamps,
            "historical_overlap":
                len(overlap),
            "source_clock_mismatches":
                source_clock_mismatches,
            "ohlc_errors": ohlc_errors,
            "identity_errors": identity_errors,
            "invalid_hourly_intervals":
                len(invalid_intervals),
            "multi_hour_gaps":
                len(multi_hour_gaps),
            "gap_hour_distribution": dict(
                sorted(
                    Counter(
                        multi_hour_gaps
                    ).items()
                )
            ),
            "largest_gap_hours": (
                max(multi_hour_gaps)
                if multi_hour_gaps
                else 1
            ),
            "multi_hour_gaps_are_informational":
                True,
        },
        "errors": errors,
    }

    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output.write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )

    print()
    print("POST-2026H1 ACQUISITION AUDIT")
    print("=" * 76)
    print("Status:", payload["status"])
    print("Rows:", len(rows))
    print("Historical endpoint UTC:", historical_end)
    print("First new candle UTC:    ", first_utc)
    print("Last new candle UTC:     ", last_utc)
    print("Initial gap hours:       ", initial_gap_hours)
    print("Duplicate timestamps:    ", duplicate_timestamps)
    print("Historical overlap:      ", len(overlap))
    print("Source clock mismatches: ", source_clock_mismatches)
    print("OHLC errors:             ", ohlc_errors)
    print("Identity errors:         ", identity_errors)
    print("Invalid intervals:       ", len(invalid_intervals))
    print("Multi-hour gaps:         ", len(multi_hour_gaps))
    print(
        "Gap distribution:        ",
        dict(sorted(Counter(multi_hour_gaps).items())),
    )
    print("Raw SHA-256:             ", sha256(raw))
    print("Metadata SHA-256:        ", sha256(metadata_path))
    print("Receipt:                 ", output)

    if errors:
        print()
        print("ERRORS")

        for error in errors:
            print("-", error)

        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

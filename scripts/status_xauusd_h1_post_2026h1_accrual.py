#!/usr/bin/env python3
"""Report progress toward the frozen post-2026H1 accrual gate.

Reads only quarantine candles, metadata, manifests, audits, and protocol.
It does not import or execute the swing engine and does not load labels.
"""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

PROTOCOL_PATH = (
    ROOT
    / "benchmarks"
    / "protocols"
    / "XAUUSD_H1_post_2026H1_locked_protocol.json"
)

QUARANTINE_ROOT = (
    ROOT
    / "benchmarks"
    / "data"
    / "quarantine"
    / "XAUUSD"
    / "H1"
    / "post_2026H1"
)

OUTPUT = (
    ROOT
    / "benchmarks"
    / "reports"
    / "XAUUSD_H1_post_2026H1_accrual_status.json"
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


def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(
        value.replace("Z", "+00:00")
    )

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)


def main() -> int:
    protocol = json.loads(
        PROTOCOL_PATH.read_text(encoding="utf-8")
    )

    accrual = protocol["accrual_requirements"]
    required_bars = int(
        accrual["minimum_unique_h1_bars"]
    )
    required_end = parse_utc(
        accrual["not_before_utc"]
    )

    manifest_paths = sorted(
        QUARANTINE_ROOT.glob(
            "*/snapshot_manifest.json"
        )
    )

    if not manifest_paths:
        raise SystemExit(
            "No immutable quarantine snapshots found."
        )

    errors: list[str] = []
    tranche_rows: list[dict] = []

    candles_by_utc: dict[
        datetime,
        tuple[Decimal, Decimal, Decimal, Decimal],
    ] = {}

    total_rows = 0
    exact_duplicate_rows = 0
    conflicting_ohlc_rows = 0

    for manifest_path in manifest_paths:
        snapshot_root = manifest_path.parent

        manifest = json.loads(
            manifest_path.read_text(encoding="utf-8")
        )

        if (
            manifest.get("status")
            != "QUARANTINED_UNLABELED_ACCRUAL_TRANCHE"
        ):
            errors.append(
                f"{snapshot_root.name}: invalid snapshot status"
            )

        controls = manifest.get(
            "contamination_controls",
            {},
        )

        if any(
            (
                controls.get("labels_exist"),
                controls.get("predictions_exist"),
                controls.get("swing_engine_executed"),
                controls.get("v2_3_evaluated"),
            )
        ):
            errors.append(
                f"{snapshot_root.name}: contamination control failed"
            )

        files = manifest["files"]

        raw = snapshot_root / files["raw"]["path"]
        metadata_path = (
            snapshot_root
            / files["metadata"]["path"]
        )
        audit_path = (
            snapshot_root
            / files["audit"]["path"]
        )

        for label, path in (
            ("raw", raw),
            ("metadata", metadata_path),
            ("audit", audit_path),
        ):
            if not path.exists():
                errors.append(
                    f"{snapshot_root.name}: missing {label} file"
                )
                continue

            expected_hash = files[label]["sha256"]
            actual_hash = sha256(path)

            if actual_hash != expected_hash:
                errors.append(
                    f"{snapshot_root.name}: "
                    f"{label} SHA-256 mismatch"
                )

        audit = json.loads(
            audit_path.read_text(encoding="utf-8")
        )

        if audit.get("status") != "PASS":
            errors.append(
                f"{snapshot_root.name}: acquisition audit failed"
            )

        with metadata_path.open(
            "r",
            encoding="utf-8-sig",
            newline="",
        ) as handle:
            metadata = dict(csv.reader(handle))

        if metadata.get("contains_labels") != "false":
            errors.append(
                f"{snapshot_root.name}: labels flag is not false"
            )

        if (
            metadata.get("contains_predictions")
            != "false"
        ):
            errors.append(
                f"{snapshot_root.name}: predictions flag is not false"
            )

        if (
            metadata.get("engine_version_evaluated")
            != "none"
        ):
            errors.append(
                f"{snapshot_root.name}: engine evaluation flag changed"
            )

        offset_seconds = int(
            metadata[
                "server_minus_gmt_seconds_at_export"
            ]
        )

        tranche_times: list[datetime] = []
        tranche_count = 0

        with raw.open(
            "r",
            encoding="utf-8-sig",
            newline="",
        ) as handle:
            for row in csv.DictReader(handle):
                source_clock = datetime.fromtimestamp(
                    int(row["timestamp_epoch"]),
                    tz=timezone.utc,
                ).replace(tzinfo=None)

                normalized_utc = (
                    source_clock
                    - timedelta(
                        seconds=offset_seconds
                    )
                ).replace(tzinfo=timezone.utc)

                ohlc = (
                    Decimal(row["open"]),
                    Decimal(row["high"]),
                    Decimal(row["low"]),
                    Decimal(row["close"]),
                )

                existing = candles_by_utc.get(
                    normalized_utc
                )

                if existing is None:
                    candles_by_utc[
                        normalized_utc
                    ] = ohlc
                elif existing == ohlc:
                    exact_duplicate_rows += 1
                else:
                    conflicting_ohlc_rows += 1
                    errors.append(
                        f"{snapshot_root.name}: "
                        f"conflicting OHLC at "
                        f"{normalized_utc.isoformat()}"
                    )

                tranche_times.append(
                    normalized_utc
                )
                tranche_count += 1
                total_rows += 1

        tranche_rows.append(
            {
                "snapshot_id": manifest["snapshot_id"],
                "rows": tranche_count,
                "first_utc": min(
                    tranche_times
                ).isoformat(),
                "last_utc": max(
                    tranche_times
                ).isoformat(),
            }
        )

    ordered_times = sorted(candles_by_utc)

    first_utc = ordered_times[0]
    last_utc = ordered_times[-1]
    unique_bars = len(ordered_times)

    bars_remaining = max(
        0,
        required_bars - unique_bars,
    )

    bars_gate_passed = (
        unique_bars >= required_bars
    )
    date_gate_passed = (
        last_utc >= required_end
    )

    accrual_gate_passed = (
        bars_gate_passed
        and date_gate_passed
        and not errors
    )

    payload = {
        "protocol_id": protocol["protocol_id"],
        "generated_at_utc": datetime.now(
            timezone.utc
        ).isoformat(timespec="seconds"),
        "status": (
            "READY_FOR_DETERMINISTIC_WINDOW_SELECTION"
            if accrual_gate_passed
            else "ACCRUING_UNLABELED_QUARANTINED_CANDLES"
        ),
        "policy": {
            "labels_loaded": False,
            "predictions_loaded": False,
            "swing_engine_imported": False,
            "swing_engine_executed": False,
        },
        "coverage": {
            "tranches": len(manifest_paths),
            "raw_rows": total_rows,
            "unique_normalized_h1_bars": unique_bars,
            "exact_duplicate_rows": (
                exact_duplicate_rows
            ),
            "conflicting_ohlc_rows": (
                conflicting_ohlc_rows
            ),
            "first_utc": first_utc.isoformat(),
            "last_utc": last_utc.isoformat(),
        },
        "gates": {
            "required_unique_h1_bars": required_bars,
            "bars_remaining": bars_remaining,
            "bars_gate_passed": bars_gate_passed,
            "required_not_before_utc": (
                required_end.isoformat()
            ),
            "date_gate_passed": date_gate_passed,
            "all_requirements_passed": (
                accrual_gate_passed
            ),
        },
        "tranches": tranche_rows,
        "errors": errors,
    }

    OUTPUT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUTPUT.write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )

    print()
    print("POST-2026H1 ACCRUAL STATUS")
    print("=" * 76)
    print("Status:", payload["status"])
    print("Immutable tranches:      ", len(manifest_paths))
    print("Raw rows:                ", total_rows)
    print("Unique normalized bars:  ", unique_bars)
    print("Exact duplicate rows:    ", exact_duplicate_rows)
    print("Conflicting OHLC rows:   ", conflicting_ohlc_rows)
    print("First UTC candle:        ", first_utc)
    print("Latest UTC candle:       ", last_utc)
    print("Required bars:           ", required_bars)
    print("Bars remaining:          ", bars_remaining)
    print("Bars gate passed:        ", bars_gate_passed)
    print("Required coverage date:  ", required_end)
    print("Date gate passed:        ", date_gate_passed)
    print("All requirements passed: ", accrual_gate_passed)
    print("Report:                  ", OUTPUT)

    if errors:
        print()
        print("ERRORS")

        for error in errors:
            print("-", error)

        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

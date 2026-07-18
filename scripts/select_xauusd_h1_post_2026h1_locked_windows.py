#!/usr/bin/env python3
"""Deterministically select post-2026H1 locked benchmark windows.

The selector:

- loads no labels or predictions;
- never imports or executes the swing engine;
- verifies every immutable quarantine snapshot;
- refuses to proceed until every frozen accrual gate passes;
- selects windows using chronology and bar indices only;
- fails on conflicting OHLC values;
- never overwrites an existing locked-window set.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

DEFAULT_PROTOCOL = (
    ROOT
    / "benchmarks"
    / "protocols"
    / "XAUUSD_H1_post_2026H1_locked_protocol.json"
)

DEFAULT_QUARANTINE_ROOT = (
    ROOT
    / "benchmarks"
    / "data"
    / "quarantine"
    / "XAUUSD"
    / "H1"
    / "post_2026H1"
)

DEFAULT_OUTPUT_PARENT = (
    ROOT
    / "benchmarks"
    / "data"
    / "locked"
    / "XAUUSD"
    / "H1"
    / "post_2026H1"
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


def sha256_json(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    return hashlib.sha256(encoded).hexdigest()


def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(
        value.replace("Z", "+00:00")
    )

    if parsed.tzinfo is None:
        parsed = parsed.replace(
            tzinfo=timezone.utc
        )

    return parsed.astimezone(timezone.utc)


def utc_text(value: datetime) -> str:
    return (
        value.astimezone(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def read_metadata(path: Path) -> dict[str, str]:
    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        return dict(csv.reader(handle))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__
    )

    parser.add_argument(
        "--protocol",
        type=Path,
        default=DEFAULT_PROTOCOL,
    )
    parser.add_argument(
        "--quarantine-root",
        type=Path,
        default=DEFAULT_QUARANTINE_ROOT,
    )
    parser.add_argument(
        "--output-parent",
        type=Path,
        default=DEFAULT_OUTPUT_PARENT,
    )

    return parser.parse_args()


def verify_file(
    path: Path,
    expected_sha256: str,
    *,
    description: str,
) -> None:
    if not path.exists():
        raise SystemExit(
            f"REFUSED: missing {description}: {path}"
        )

    actual = sha256(path)

    if actual != expected_sha256:
        raise SystemExit(
            f"REFUSED: {description} SHA-256 mismatch: "
            f"{path}"
        )


def load_snapshot(
    manifest_path: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    snapshot_root = manifest_path.parent

    manifest = json.loads(
        manifest_path.read_text(encoding="utf-8")
    )

    if (
        manifest.get("status")
        != "QUARANTINED_UNLABELED_ACCRUAL_TRANCHE"
    ):
        raise SystemExit(
            "REFUSED: invalid snapshot status in "
            f"{snapshot_root}"
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
        raise SystemExit(
            "REFUSED: contaminated snapshot: "
            f"{snapshot_root}"
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

    verify_file(
        raw,
        files["raw"]["sha256"],
        description="raw candle file",
    )
    verify_file(
        metadata_path,
        files["metadata"]["sha256"],
        description="metadata file",
    )
    verify_file(
        audit_path,
        files["audit"]["sha256"],
        description="acquisition audit",
    )

    audit = json.loads(
        audit_path.read_text(encoding="utf-8")
    )

    if audit.get("status") != "PASS":
        raise SystemExit(
            "REFUSED: snapshot audit is not PASS: "
            f"{snapshot_root}"
        )

    policy = audit.get("policy", {})

    if any(
        (
            policy.get("labels_loaded"),
            policy.get("predictions_loaded"),
            policy.get("swing_engine_executed"),
        )
    ):
        raise SystemExit(
            "REFUSED: snapshot audit indicates "
            f"contamination: {snapshot_root}"
        )

    metadata = read_metadata(metadata_path)

    required_metadata = {
        "dataset_role":
            "UNLABELED_QUARANTINED_RAW_CANDLES",
        "timeframe": "PERIOD_H1",
        "contains_labels": "false",
        "contains_predictions": "false",
        "engine_version_evaluated": "none",
    }

    for key, expected in required_metadata.items():
        if metadata.get(key) != expected:
            raise SystemExit(
                "REFUSED: metadata policy failure in "
                f"{snapshot_root}: {key}"
            )

    try:
        offset_seconds = int(
            metadata[
                "server_minus_gmt_seconds_at_export"
            ]
        )
    except (KeyError, ValueError) as exc:
        raise SystemExit(
            "REFUSED: invalid server offset in "
            f"{snapshot_root}"
        ) from exc

    rows: list[dict[str, Any]] = []

    with raw.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        reader = csv.DictReader(handle)

        for line_number, row in enumerate(
            reader,
            start=2,
        ):
            try:
                source_clock = (
                    datetime.fromtimestamp(
                        int(row["timestamp_epoch"]),
                        tz=timezone.utc,
                    ).replace(tzinfo=None)
                )

                displayed_clock = datetime.strptime(
                    row["timestamp_server"],
                    "%Y.%m.%d %H:%M:%S",
                )

                if source_clock != displayed_clock:
                    raise ValueError(
                        "server-clock fields disagree"
                    )

                timestamp_utc = (
                    source_clock
                    - timedelta(
                        seconds=offset_seconds
                    )
                ).replace(tzinfo=timezone.utc)

                rows.append(
                    {
                        "timestamp_utc": timestamp_utc,
                        "open": Decimal(row["open"]),
                        "high": Decimal(row["high"]),
                        "low": Decimal(row["low"]),
                        "close": Decimal(row["close"]),
                        "tick_volume": int(
                            row["tick_volume"]
                        ),
                        "volume": int(row["volume"]),
                        "spread_price": Decimal(
                            row["spread_price"]
                        ),
                        "symbol": row["symbol"],
                        "timeframe": row["timeframe"],
                        "snapshot_id": manifest[
                            "snapshot_id"
                        ],
                    }
                )

            except Exception as exc:
                raise SystemExit(
                    "REFUSED: failed to parse "
                    f"{raw}, line {line_number}: {exc}"
                ) from exc

    return rows, {
        "snapshot_id": manifest["snapshot_id"],
        "manifest_path": display_path(
            manifest_path
        ),
        "manifest_sha256": sha256(manifest_path),
        "raw_sha256": files["raw"]["sha256"],
        "metadata_sha256": (
            files["metadata"]["sha256"]
        ),
        "audit_sha256": files["audit"]["sha256"],
        "rows": len(rows),
    }


def combine_snapshots(
    manifest_paths: list[Path],
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    int,
    int,
]:
    combined: dict[
        datetime,
        dict[str, Any],
    ] = {}

    provenance: list[dict[str, Any]] = []
    exact_duplicate_rows = 0
    auxiliary_difference_rows = 0

    for manifest_path in manifest_paths:
        rows, snapshot_info = load_snapshot(
            manifest_path
        )
        provenance.append(snapshot_info)

        for row in rows:
            timestamp = row["timestamp_utc"]
            existing = combined.get(timestamp)

            if existing is None:
                combined[timestamp] = {
                    **row,
                    "source_snapshot_ids": [
                        row["snapshot_id"]
                    ],
                }
                continue

            existing_ohlc = (
                existing["open"],
                existing["high"],
                existing["low"],
                existing["close"],
            )

            incoming_ohlc = (
                row["open"],
                row["high"],
                row["low"],
                row["close"],
            )

            if existing_ohlc != incoming_ohlc:
                raise SystemExit(
                    "REFUSED: conflicting OHLC at "
                    f"{utc_text(timestamp)}"
                )

            exact_duplicate_rows += 1

            auxiliary_existing = (
                existing["tick_volume"],
                existing["volume"],
                existing["spread_price"],
            )

            auxiliary_incoming = (
                row["tick_volume"],
                row["volume"],
                row["spread_price"],
            )

            if auxiliary_existing != auxiliary_incoming:
                auxiliary_difference_rows += 1

            if (
                row["snapshot_id"]
                not in existing["source_snapshot_ids"]
            ):
                existing["source_snapshot_ids"].append(
                    row["snapshot_id"]
                )

    ordered = [
        combined[timestamp]
        for timestamp in sorted(combined)
    ]

    return (
        ordered,
        provenance,
        exact_duplicate_rows,
        auxiliary_difference_rows,
    )


def select_windows(
    bars: list[dict[str, Any]],
    protocol: dict[str, Any],
) -> list[dict[str, Any]]:
    selection = protocol["window_selection"]

    leading_guard = int(
        selection["leading_guard_bars"]
    )
    trailing_guard = int(
        selection["trailing_guard_bars"]
    )
    bucket_count = int(
        selection["bucket_count"]
    )
    window_bars = int(
        selection["window_bars"]
    )

    usable_start = leading_guard
    usable_end = len(bars) - trailing_guard
    usable_count = usable_end - usable_start

    if usable_count <= 0:
        raise SystemExit(
            "REFUSED: guards leave no usable bars"
        )

    windows: list[dict[str, Any]] = []

    for bucket_index in range(bucket_count):
        bucket_start = (
            usable_start
            + bucket_index
            * usable_count
            // bucket_count
        )

        bucket_end = (
            usable_start
            + (bucket_index + 1)
            * usable_count
            // bucket_count
        )

        bucket_size = bucket_end - bucket_start

        if bucket_size < window_bars:
            raise SystemExit(
                "REFUSED: bucket "
                f"{bucket_index + 1} contains only "
                f"{bucket_size} bars; {window_bars} required"
            )

        window_start = (
            bucket_start
            + (bucket_size - window_bars) // 2
        )
        window_end = (
            window_start + window_bars
        )

        windows.append(
            {
                "window_number": bucket_index + 1,
                "bucket_start_index": bucket_start,
                "bucket_end_index_exclusive": (
                    bucket_end
                ),
                "bucket_bars": bucket_size,
                "start_index": window_start,
                "end_index_exclusive": window_end,
                "bars": window_bars,
                "first_utc": utc_text(
                    bars[window_start][
                        "timestamp_utc"
                    ]
                ),
                "last_utc": utc_text(
                    bars[window_end - 1][
                        "timestamp_utc"
                    ]
                ),
            }
        )

    for left, right in zip(
        windows,
        windows[1:],
    ):
        if (
            left["end_index_exclusive"]
            > right["start_index"]
        ):
            raise SystemExit(
                "REFUSED: selected windows overlap"
            )

    return windows


def write_window(
    path: Path,
    bars: list[dict[str, Any]],
    window: dict[str, Any],
) -> None:
    start = int(window["start_index"])
    end = int(window["end_index_exclusive"])

    with path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.writer(
            handle,
            lineterminator="\n",
        )

        writer.writerow(
            [
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
        )

        for local_index, global_index in enumerate(
            range(start, end)
        ):
            row = bars[global_index]

            writer.writerow(
                [
                    local_index,
                    global_index,
                    utc_text(
                        row["timestamp_utc"]
                    ),
                    str(row["open"]),
                    str(row["high"]),
                    str(row["low"]),
                    str(row["close"]),
                    row["tick_volume"],
                    row["volume"],
                    str(row["spread_price"]),
                    row["symbol"],
                    row["timeframe"],
                    "|".join(
                        sorted(
                            row[
                                "source_snapshot_ids"
                            ]
                        )
                    ),
                ]
            )


def main() -> int:
    args = parse_args()

    protocol_path = args.protocol.resolve()
    quarantine_root = (
        args.quarantine_root.resolve()
    )
    output_parent = (
        args.output_parent.resolve()
    )

    if not protocol_path.exists():
        raise SystemExit(
            f"REFUSED: missing protocol {protocol_path}"
        )

    protocol = json.loads(
        protocol_path.read_text(encoding="utf-8")
    )

    manifest_paths = sorted(
        quarantine_root.glob(
            "*/snapshot_manifest.json"
        )
    )

    if not manifest_paths:
        raise SystemExit(
            "REFUSED: no quarantine snapshots found"
        )

    (
        bars,
        provenance,
        duplicate_rows,
        auxiliary_differences,
    ) = combine_snapshots(manifest_paths)

    accrual = protocol["accrual_requirements"]

    required_bars = int(
        accrual["minimum_unique_h1_bars"]
    )

    required_end = parse_utc(
        accrual["not_before_utc"]
    )

    latest_utc = bars[-1]["timestamp_utc"]
    bars_gate = len(bars) >= required_bars
    date_gate = latest_utc >= required_end

    print()
    print("LOCKED-WINDOW SELECTION GATE")
    print("=" * 76)
    print("Protocol:", protocol["protocol_id"])
    print("Snapshots:", len(manifest_paths))
    print("Unique normalized bars:", len(bars))
    print("Required bars:", required_bars)
    print("Bars gate passed:", bars_gate)
    print("Latest UTC:", latest_utc)
    print("Required UTC:", required_end)
    print("Date gate passed:", date_gate)
    print("Exact duplicate rows:", duplicate_rows)
    print(
        "Auxiliary differences on duplicate OHLC:",
        auxiliary_differences,
    )

    if not (bars_gate and date_gate):
        raise SystemExit(
            "REFUSED: frozen accrual requirements "
            "have not all passed"
        )

    windows = select_windows(
        bars,
        protocol,
    )

    protocol_id = protocol["protocol_id"]

    output_root = (
        output_parent / protocol_id
    )

    staging_root = (
        output_parent
        / f".staging-{protocol_id}"
    )

    if output_root.exists():
        raise SystemExit(
            "REFUSED: immutable locked-window set "
            f"already exists: {output_root}"
        )

    if staging_root.exists():
        raise SystemExit(
            "REFUSED: stale staging directory exists: "
            f"{staging_root}"
        )

    output_parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    staging_root.mkdir()

    try:
        window_files = []

        for window in windows:
            filename = (
                f"window_{window['window_number']:02d}.csv"
            )

            path = staging_root / filename

            write_window(
                path,
                bars,
                window,
            )

            window_files.append(
                {
                    **window,
                    "path": filename,
                    "sha256": sha256(path),
                }
            )

        selection_basis = [
            {
                "global_bar_index": index,
                "timestamp_utc": utc_text(
                    row["timestamp_utc"]
                ),
            }
            for index, row in enumerate(bars)
        ]

        manifest = {
            "protocol_id": protocol_id,
            "status": (
                "WINDOWS_SELECTED_UNLABELED_"
                "NOT_EVALUATED"
            ),
            "immutable_after_commit": True,
            "generated_at_utc": datetime.now(
                timezone.utc
            ).isoformat(timespec="seconds"),
            "protocol": {
                "path": display_path(
                    protocol_path
                ),
                "sha256": sha256(protocol_path),
            },
            "policy": {
                "labels_loaded": False,
                "predictions_loaded": False,
                "swing_engine_imported": False,
                "swing_engine_executed": False,
                "selection_uses_prices": False,
                "selection_uses_predictions": False,
                "selection_uses_chronology_and_indices_only": (
                    True
                ),
            },
            "combined_input": {
                "snapshots": provenance,
                "unique_normalized_bars": len(bars),
                "first_utc": utc_text(
                    bars[0]["timestamp_utc"]
                ),
                "last_utc": utc_text(
                    bars[-1]["timestamp_utc"]
                ),
                "exact_duplicate_rows": duplicate_rows,
                "auxiliary_differences_on_duplicate_ohlc": (
                    auxiliary_differences
                ),
                "selection_basis_sha256": (
                    sha256_json(selection_basis)
                ),
            },
            "selection_parameters": (
                protocol["window_selection"]
            ),
            "windows": window_files,
            "contamination_controls": {
                "labels_exist": False,
                "predictions_exist": False,
                "swing_engine_executed": False,
                "candidate_evaluated": False,
                "baseline_evaluated": False,
            },
        }

        manifest_path = (
            staging_root
            / "selection_manifest.json"
        )

        manifest_path.write_text(
            json.dumps(
                manifest,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        staging_root.replace(output_root)

    except BaseException:
        if staging_root.exists():
            shutil.rmtree(staging_root)

        raise

    print()
    print("LOCKED WINDOWS SELECTED")
    print("=" * 76)
    print("Output:", output_root)

    for window in windows:
        print(
            f"Window {window['window_number']:02d}: "
            f"{window['first_utc']} through "
            f"{window['last_utc']}"
        )

    print()
    print(
        "No labels, predictions, or swing-engine "
        "execution occurred."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

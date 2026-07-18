#!/usr/bin/env python3
"""Ingest one immutable post-2026H1 XAUUSD H1 acquisition tranche.

The ingester:

- loads no labels or predictions;
- never imports or executes the swing engine;
- preserves source CSV bytes exactly;
- audits the acquisition before publication;
- rejects timestamp/OHLC conflicts and historical backfills;
- requires at least one genuinely new normalized UTC candle;
- never overwrites an existing snapshot.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

QUARANTINE_ROOT = (
    ROOT
    / "benchmarks"
    / "data"
    / "quarantine"
    / "XAUUSD"
    / "H1"
    / "post_2026H1"
)

AUDITOR = (
    ROOT
    / "scripts"
    / "audit_xauusd_h1_post_2026h1_acquisition.py"
)

CANONICAL_RAW_NAME = "XAUUSD_H1_raw.csv"
CANONICAL_METADATA_NAME = "XAUUSD_H1_raw.meta.csv"
AUDIT_NAME = "acquisition_audit.json"
MANIFEST_NAME = "snapshot_manifest.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def read_metadata(path: Path) -> dict[str, str]:
    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        return dict(csv.reader(handle))


def require_metadata(
    metadata: dict[str, str],
) -> None:
    required = {
        "dataset_role":
            "UNLABELED_QUARANTINED_RAW_CANDLES",
        "timeframe": "PERIOD_H1",
        "contains_labels": "false",
        "contains_predictions": "false",
        "engine_version_evaluated": "none",
    }

    errors = []

    for key, expected in required.items():
        actual = metadata.get(key)

        if actual != expected:
            errors.append(
                f"{key}: expected {expected!r}, "
                f"got {actual!r}"
            )

    if errors:
        raise SystemExit(
            "REFUSED: metadata policy failed:\n- "
            + "\n- ".join(errors)
        )


def parse_exported_at_gmt(
    value: str,
) -> datetime:
    try:
        return datetime.strptime(
            value,
            "%Y.%m.%d %H:%M:%S",
        ).replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise SystemExit(
            "REFUSED: invalid exported_at_gmt "
            f"value {value!r}"
        ) from exc


def snapshot_stamp(
    exported_at_gmt: datetime,
) -> str:
    return exported_at_gmt.strftime(
        "%Y%m%dT%H%M%SZ"
    )


def load_candles(
    raw: Path,
    metadata: dict[str, str],
) -> tuple[
    dict[
        datetime,
        tuple[
            Decimal,
            Decimal,
            Decimal,
            Decimal,
        ],
    ],
    int,
    int,
]:
    try:
        offset_seconds = int(
            metadata[
                "server_minus_gmt_seconds_at_export"
            ]
        )
    except (KeyError, ValueError) as exc:
        raise SystemExit(
            "REFUSED: invalid broker-server UTC offset"
        ) from exc

    candles: dict[
        datetime,
        tuple[
            Decimal,
            Decimal,
            Decimal,
            Decimal,
        ],
    ] = {}

    row_count = 0
    exact_duplicates = 0

    with raw.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        reader = csv.DictReader(handle)

        required_columns = {
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
        }

        if set(reader.fieldnames or []) != required_columns:
            raise SystemExit(
                "REFUSED: unexpected raw CSV columns"
            )

        for line_number, row in enumerate(
            reader,
            start=2,
        ):
            row_count += 1

            try:
                numeric_clock = (
                    datetime.fromtimestamp(
                        int(row["timestamp_epoch"]),
                        tz=timezone.utc,
                    ).replace(tzinfo=None)
                )

                server_clock = datetime.strptime(
                    row["timestamp_server"],
                    "%Y.%m.%d %H:%M:%S",
                )

                if numeric_clock != server_clock:
                    raise ValueError(
                        "numeric and displayed "
                        "server clocks differ"
                    )

                normalized_utc = (
                    numeric_clock
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

                existing = candles.get(
                    normalized_utc
                )

                if existing is None:
                    candles[
                        normalized_utc
                    ] = ohlc
                elif existing == ohlc:
                    exact_duplicates += 1
                else:
                    raise ValueError(
                        "conflicting duplicate OHLC"
                    )

            except Exception as exc:
                raise SystemExit(
                    "REFUSED: raw row "
                    f"{line_number} failed: {exc}"
                ) from exc

    if not candles:
        raise SystemExit(
            "REFUSED: raw acquisition has no candles"
        )

    return (
        candles,
        row_count,
        exact_duplicates,
    )


def verify_snapshot_files(
    snapshot_root: Path,
    manifest: dict,
) -> tuple[Path, Path]:
    files = manifest["files"]

    raw = (
        snapshot_root
        / files["raw"]["path"]
    )

    metadata = (
        snapshot_root
        / files["metadata"]["path"]
    )

    audit = (
        snapshot_root
        / files["audit"]["path"]
    )

    for label, path in (
        ("raw", raw),
        ("metadata", metadata),
        ("audit", audit),
    ):
        if not path.exists():
            raise SystemExit(
                "REFUSED: existing snapshot "
                f"{snapshot_root.name} is missing "
                f"{label}"
            )

        expected = files[label]["sha256"]
        actual = sha256(path)

        if actual != expected:
            raise SystemExit(
                "REFUSED: existing snapshot "
                f"{snapshot_root.name} has a "
                f"{label} hash mismatch"
            )

    controls = manifest.get(
        "contamination_controls",
        {},
    )

    if any(
        (
            controls.get("labels_exist"),
            controls.get("predictions_exist"),
            controls.get(
                "swing_engine_executed"
            ),
            controls.get("v2_3_evaluated"),
        )
    ):
        raise SystemExit(
            "REFUSED: existing snapshot "
            f"{snapshot_root.name} is contaminated"
        )

    return raw, metadata


def load_existing_candles() -> dict[
    datetime,
    tuple[
        Decimal,
        Decimal,
        Decimal,
        Decimal,
    ],
]:
    combined: dict[
        datetime,
        tuple[
            Decimal,
            Decimal,
            Decimal,
            Decimal,
        ],
    ] = {}

    manifests = sorted(
        QUARANTINE_ROOT.glob(
            "*/snapshot_manifest.json"
        )
    )

    for manifest_path in manifests:
        snapshot_root = manifest_path.parent

        manifest = json.loads(
            manifest_path.read_text(
                encoding="utf-8"
            )
        )

        if (
            manifest.get("status")
            != "QUARANTINED_UNLABELED_ACCRUAL_TRANCHE"
        ):
            raise SystemExit(
                "REFUSED: invalid existing snapshot "
                f"status in {snapshot_root.name}"
            )

        raw, metadata_path = (
            verify_snapshot_files(
                snapshot_root,
                manifest,
            )
        )

        metadata = read_metadata(
            metadata_path
        )

        candles, _, _ = load_candles(
            raw,
            metadata,
        )

        for timestamp, ohlc in candles.items():
            existing = combined.get(timestamp)

            if existing is None:
                combined[timestamp] = ohlc
            elif existing != ohlc:
                raise SystemExit(
                    "REFUSED: existing snapshots "
                    "contain conflicting OHLC at "
                    f"{timestamp.isoformat()}"
                )

    return combined


def run_auditor(
    raw: Path,
    metadata: Path,
    output: Path,
) -> dict:
    command = [
        sys.executable,
        str(AUDITOR),
        "--raw",
        str(raw),
        "--metadata",
        str(metadata),
        "--output",
        str(output),
    ]

    process = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    if process.stdout:
        print(process.stdout, end="")

    if process.stderr:
        print(
            process.stderr,
            file=sys.stderr,
            end="",
        )

    if process.returncode != 0:
        raise SystemExit(
            "REFUSED: acquisition audit failed"
        )

    audit = json.loads(
        output.read_text(encoding="utf-8")
    )

    if audit.get("status") != "PASS":
        raise SystemExit(
            "REFUSED: audit receipt is not PASS"
        )

    return audit


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__
    )

    parser.add_argument(
        "--raw",
        type=Path,
        required=True,
        help="New MT5 raw candle CSV.",
    )

    parser.add_argument(
        "--metadata",
        type=Path,
        required=True,
        help="Matching MT5 metadata CSV.",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    source_raw = args.raw.resolve()
    source_metadata = args.metadata.resolve()

    for path in (
        source_raw,
        source_metadata,
        AUDITOR,
    ):
        if not path.exists():
            raise SystemExit(
                f"REFUSED: missing required file {path}"
            )

    metadata = read_metadata(
        source_metadata
    )

    require_metadata(metadata)

    exported_at_gmt = parse_exported_at_gmt(
        metadata.get(
            "exported_at_gmt",
            "",
        )
    )

    stamp = snapshot_stamp(
        exported_at_gmt
    )

    snapshot_root = (
        QUARANTINE_ROOT / stamp
    )

    staging_root = (
        QUARANTINE_ROOT
        / f".staging-{stamp}"
    )

    if snapshot_root.exists():
        raise SystemExit(
            "REFUSED: immutable snapshot already "
            f"exists: {snapshot_root}"
        )

    if staging_root.exists():
        raise SystemExit(
            "REFUSED: stale staging directory "
            f"exists: {staging_root}"
        )

    incoming, raw_rows, internal_duplicates = (
        load_candles(
            source_raw,
            metadata,
        )
    )

    existing = load_existing_candles()

    exact_overlap = 0
    conflicting_overlap = 0
    new_timestamps: list[datetime] = []

    for timestamp, ohlc in incoming.items():
        prior = existing.get(timestamp)

        if prior is None:
            new_timestamps.append(timestamp)
        elif prior == ohlc:
            exact_overlap += 1
        else:
            conflicting_overlap += 1

    if conflicting_overlap:
        raise SystemExit(
            "REFUSED: incoming acquisition has "
            f"{conflicting_overlap} OHLC conflicts "
            "with immutable snapshots"
        )

    if not new_timestamps:
        raise SystemExit(
            "REFUSED: acquisition contains no new "
            "normalized UTC candles"
        )

    if existing:
        existing_latest = max(existing)

        backfills = [
            timestamp
            for timestamp in new_timestamps
            if timestamp <= existing_latest
        ]

        if backfills:
            raise SystemExit(
                "REFUSED: append-only policy rejects "
                f"{len(backfills)} historical backfill "
                "timestamps"
            )
    else:
        existing_latest = None

    QUARANTINE_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    staging_root.mkdir()

    try:
        staged_raw = (
            staging_root
            / CANONICAL_RAW_NAME
        )

        staged_metadata = (
            staging_root
            / CANONICAL_METADATA_NAME
        )

        staged_audit = (
            staging_root
            / AUDIT_NAME
        )

        staged_manifest = (
            staging_root
            / MANIFEST_NAME
        )

        # copyfile preserves the original bytes.
        shutil.copyfile(
            source_raw,
            staged_raw,
        )

        shutil.copyfile(
            source_metadata,
            staged_metadata,
        )

        audit = run_auditor(
            staged_raw,
            staged_metadata,
            staged_audit,
        )

        manifest = {
            "snapshot_id": (
                "XAUUSD_H1_POST_2026H1_"
                f"{stamp}"
            ),
            "status": (
                "QUARANTINED_UNLABELED_"
                "ACCRUAL_TRANCHE"
            ),
            "immutable_after_commit": True,
            "eligible_for_engine_evaluation": False,
            "eligible_for_labeling": False,
            "benchmark_status": (
                "NOT_YET_A_BENCHMARK"
            ),
            "source": {
                "symbol": metadata.get("symbol"),
                "timeframe": metadata.get(
                    "timeframe"
                ),
                "account_server": metadata.get(
                    "account_server"
                ),
                "exported_at_gmt": metadata.get(
                    "exported_at_gmt"
                ),
                "server_minus_gmt_seconds": int(
                    metadata[
                        "server_minus_gmt_seconds_at_export"
                    ]
                ),
            },
            "coverage": audit["coverage"],
            "ingestion": {
                "raw_rows": raw_rows,
                "internal_exact_duplicate_rows": (
                    internal_duplicates
                ),
                "existing_unique_bars_before": (
                    len(existing)
                ),
                "exact_overlap_with_existing": (
                    exact_overlap
                ),
                "new_unique_bars": (
                    len(new_timestamps)
                ),
                "existing_latest_utc_before": (
                    existing_latest.isoformat()
                    if existing_latest
                    else None
                ),
                "first_new_unique_utc": (
                    min(
                        new_timestamps
                    ).isoformat()
                ),
                "last_new_unique_utc": (
                    max(
                        new_timestamps
                    ).isoformat()
                ),
            },
            "files": {
                "raw": {
                    "path": CANONICAL_RAW_NAME,
                    "sha256": sha256(
                        staged_raw
                    ),
                },
                "metadata": {
                    "path":
                        CANONICAL_METADATA_NAME,
                    "sha256": sha256(
                        staged_metadata
                    ),
                },
                "audit": {
                    "path": AUDIT_NAME,
                    "sha256": sha256(
                        staged_audit
                    ),
                },
            },
            "contamination_controls": {
                "labels_exist": False,
                "predictions_exist": False,
                "swing_engine_executed": False,
                "v2_3_evaluated": False,
            },
        }

        staged_manifest.write_text(
            json.dumps(
                manifest,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        staging_root.replace(
            snapshot_root
        )

    except BaseException:
        if staging_root.exists():
            shutil.rmtree(staging_root)

        raise

    print()
    print("QUARANTINE INGESTION COMPLETE")
    print("=" * 76)
    print("Snapshot:", snapshot_root)
    print("Raw rows:", raw_rows)
    print(
        "Existing unique bars:",
        len(existing),
    )
    print(
        "Exact overlap rows:",
        exact_overlap,
    )
    print(
        "New unique bars:",
        len(new_timestamps),
    )
    print(
        "First new UTC:",
        min(new_timestamps),
    )
    print(
        "Last new UTC:",
        max(new_timestamps),
    )
    print(
        "Raw SHA-256:",
        manifest["files"]["raw"]["sha256"],
    )
    print(
        "Metadata SHA-256:",
        manifest[
            "files"
        ]["metadata"]["sha256"],
    )
    print()
    print(
        "No labels, predictions, or swing-engine "
        "execution occurred."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

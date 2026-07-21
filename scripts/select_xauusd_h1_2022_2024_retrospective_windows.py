#!/usr/bin/env python3
"""Price-blind window selection for the 2022–2024 retrospective holdout.

Safety:
- validates source package and protocol hashes;
- uses indices and timestamps only;
- never imports detection code;
- never reads labels;
- never chooses windows using OHLC values;
- refuses overwrite.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

DEFAULT_PROTOCOL = (
    ROOT
    / "benchmarks"
    / "protocols"
    / "XAUUSD_H1_2022_2024_retrospective_locked_protocol.json"
)

DEFAULT_SOURCE_ROOT = (
    ROOT
    / "benchmarks"
    / "data"
    / "retrospective"
    / "XAUUSD"
    / "H1_2022_2024_v1"
)

DEFAULT_OUTPUT_PARENT = (
    ROOT
    / "benchmarks"
    / "data"
    / "locked"
    / "XAUUSD"
    / "H1"
    / "retrospective_2022_2024"
)

ALGORITHM_VERSION = "PRICE_BLIND_SIX_BUCKET_CENTERED_V1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path.resolve())


def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def utc_text(value: datetime) -> str:
    return (
        value.astimezone(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument(
        "--source-root",
        type=Path,
        default=DEFAULT_SOURCE_ROOT,
    )
    parser.add_argument(
        "--output-parent",
        type=Path,
        default=DEFAULT_OUTPUT_PARENT,
    )
    return parser.parse_args()


def load_canonical_bars(path: Path) -> list[dict[str, Any]]:
    bars: list[dict[str, Any]] = []
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            bars.append(
                {
                    "bar_index": int(row["bar_index"]),
                    "timestamp_utc": parse_utc(row["timestamp_utc"]),
                    # OHLC intentionally loaded only for integrity export to
                    # window CSVs; selection never inspects these fields.
                    "open": row["open"],
                    "high": row["high"],
                    "low": row["low"],
                    "close": row["close"],
                    "tick_volume": row["tick_volume"],
                    "volume": row["volume"],
                    "mean_spread": row.get("mean_spread", ""),
                    "source": row.get("source", ""),
                    "price_basis": row.get("price_basis", ""),
                }
            )
    if not bars:
        raise SystemExit("REFUSED: empty canonical source")

    for previous, current in zip(bars, bars[1:]):
        if current["timestamp_utc"] <= previous["timestamp_utc"]:
            raise SystemExit(
                "REFUSED: canonical timestamps are not strictly increasing"
            )
        if current["bar_index"] != previous["bar_index"] + 1:
            raise SystemExit(
                "REFUSED: canonical bar_index values are not sequential"
            )
    return bars


def select_windows(
    bars: list[dict[str, Any]],
    protocol: dict[str, Any],
) -> list[dict[str, Any]]:
    selection = protocol["window_selection"]
    leading_guard = int(selection["leading_guard_bars"])
    trailing_guard = int(selection["trailing_guard_bars"])
    bucket_count = int(selection["bucket_count"])
    window_bars = int(selection["window_bars"])

    usable_start = leading_guard
    usable_end = len(bars) - trailing_guard
    usable_count = usable_end - usable_start

    if usable_count <= 0:
        raise SystemExit("REFUSED: guards leave no usable bars")

    windows: list[dict[str, Any]] = []
    for bucket_index in range(bucket_count):
        bucket_start = (
            usable_start
            + bucket_index * usable_count // bucket_count
        )
        bucket_end = (
            usable_start
            + (bucket_index + 1) * usable_count // bucket_count
        )
        bucket_size = bucket_end - bucket_start
        if bucket_size < window_bars:
            raise SystemExit(
                f"REFUSED: bucket {bucket_index + 1} contains only "
                f"{bucket_size} bars; {window_bars} required"
            )

        window_start = bucket_start + (bucket_size - window_bars) // 2
        window_end = window_start + window_bars
        windows.append(
            {
                "window_number": bucket_index + 1,
                "bucket_start_index": bucket_start,
                "bucket_end_index_exclusive": bucket_end,
                "bucket_bars": bucket_size,
                "start_index": window_start,
                "end_index_exclusive": window_end,
                "bars": window_bars,
                "first_utc": utc_text(bars[window_start]["timestamp_utc"]),
                "last_utc": utc_text(
                    bars[window_end - 1]["timestamp_utc"]
                ),
            }
        )

    for left, right in zip(windows, windows[1:]):
        if left["end_index_exclusive"] > right["start_index"]:
            raise SystemExit("REFUSED: selected windows overlap")

    return windows


def write_window(
    path: Path,
    bars: list[dict[str, Any]],
    window: dict[str, Any],
) -> None:
    start = int(window["start_index"])
    end = int(window["end_index_exclusive"])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
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
                "mean_spread",
                "source",
                "price_basis",
            ]
        )
        for local_index, global_index in enumerate(range(start, end)):
            row = bars[global_index]
            writer.writerow(
                [
                    local_index,
                    global_index,
                    utc_text(row["timestamp_utc"]),
                    row["open"],
                    row["high"],
                    row["low"],
                    row["close"],
                    row["tick_volume"],
                    row["volume"],
                    row["mean_spread"],
                    row["source"],
                    row["price_basis"],
                ]
            )


def main() -> int:
    args = parse_args()
    protocol_path = args.protocol.resolve()
    source_root = args.source_root.resolve()
    output_parent = args.output_parent.resolve()
    output_root = output_parent / "windows_v1"

    if not protocol_path.exists():
        raise SystemExit(f"REFUSED: missing protocol {protocol_path}")
    if not source_root.exists():
        raise SystemExit(f"REFUSED: missing source package {source_root}")
    if output_root.exists():
        raise SystemExit(
            f"REFUSED: window package already exists: {output_root}"
        )

    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    if protocol.get("protocol_id") != (
        "XAUUSD_H1_2022_2024_RETROSPECTIVE_LOCKED_V1"
    ):
        raise SystemExit("REFUSED: unexpected protocol_id")
    if protocol.get("benchmark_type") != "RETROSPECTIVE_HOLDOUT":
        raise SystemExit("REFUSED: unexpected benchmark_type")
    if protocol.get("tuning_allowed") is not False:
        raise SystemExit("REFUSED: protocol allows tuning")
    if protocol["window_selection"].get("selection_uses_prices_or_predictions"):
        raise SystemExit(
            "REFUSED: protocol permits price/prediction-based selection"
        )

    source_manifest_path = source_root / "source_manifest.json"
    if not source_manifest_path.exists():
        raise SystemExit("REFUSED: missing source_manifest.json")
    source_manifest = json.loads(
        source_manifest_path.read_text(encoding="utf-8")
    )

    canonical_name = "XAUUSD_H1_2022_2024.real.csv.gz"
    canonical_path = source_root / canonical_name
    if not canonical_path.exists():
        raise SystemExit(f"REFUSED: missing {canonical_name}")

    expected_canonical_sha = source_manifest["files"][canonical_name]
    actual_canonical_sha = sha256(canonical_path)
    if actual_canonical_sha != expected_canonical_sha:
        raise SystemExit(
            "REFUSED: canonical source checksum mismatch "
            f"(expected {expected_canonical_sha}, got {actual_canonical_sha})"
        )

    protocol_sha = sha256(protocol_path)
    expected_protocol_sha = protocol.get("source_package", {}).get(
        "canonical_sha256"
    )
    if expected_protocol_sha and expected_protocol_sha != actual_canonical_sha:
        raise SystemExit(
            "REFUSED: protocol source_package canonical_sha256 mismatch"
        )

    bars = load_canonical_bars(canonical_path)
    # Selection uses only indices/timestamps.
    selection_bars = [
        {"timestamp_utc": bar["timestamp_utc"]} for bar in bars
    ]
    windows = select_windows(selection_bars, protocol)

    # Reattach full rows for immutable window CSV export after selection.
    for window in windows:
        start = window["start_index"]
        end = window["end_index_exclusive"]
        window["first_utc"] = utc_text(bars[start]["timestamp_utc"])
        window["last_utc"] = utc_text(bars[end - 1]["timestamp_utc"])

    staging_parent = output_parent
    staging_parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(
            prefix=".windows_v1_staging_",
            dir=str(staging_parent),
        )
    )

    try:
        window_files: dict[str, str] = {}
        for window in windows:
            name = (
                f"window_{window['window_number']:02d}_"
                f"{window['start_index']}_"
                f"{window['end_index_exclusive']}.csv"
            )
            path = staging / name
            write_window(path, bars, window)
            digest = sha256(path)
            window["file"] = name
            window["sha256"] = digest
            window_files[name] = digest

        selection_manifest = {
            "selection_id": (
                "XAUUSD_H1_2022_2024_RETROSPECTIVE_WINDOWS_V1"
            ),
            "benchmark_type": "RETROSPECTIVE_HOLDOUT",
            "protocol_id": protocol["protocol_id"],
            "protocol_sha256": protocol_sha,
            "algorithm_version": ALGORITHM_VERSION,
            "source_root": display_path(source_root),
            "canonical_source": display_path(canonical_path),
            "canonical_source_sha256": actual_canonical_sha,
            "source_bar_count": len(bars),
            "windows": windows,
            "window_files": window_files,
            "contamination_controls": {
                "labels_loaded": False,
                "predictions_loaded": False,
                "swing_engine_executed": False,
                "ohlc_inspected_for_selection": False,
                "candidate_evaluated": False,
                "baseline_evaluated": False,
                "selection_uses_prices_or_predictions": False,
            },
            "eligibility": {
                "eligible_for_tuning": False,
                "eligible_for_labeling": True,
                "eligible_for_evaluation": False,
                "prospective_test": False,
            },
        }

        manifest_path = staging / "selection_manifest.json"
        manifest_path.write_text(
            json.dumps(selection_manifest, indent=2) + "\n",
            encoding="utf-8",
        )
        # Do not embed selection_manifest_sha256 inside this file.
        # Downstream pass/adjudication/freeze evidence must hash the final
        # published bytes from disk after publication.

        if output_root.exists():
            raise SystemExit(
                f"REFUSED: window package already exists: {output_root}"
            )
        os.rename(staging, output_root)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    published_manifest = output_root / "selection_manifest.json"
    published_manifest_sha256 = sha256(published_manifest)

    print(f"Published windows: {display_path(output_root)}")
    print(f"Protocol SHA-256: {protocol_sha}")
    print(f"Canonical SHA-256: {actual_canonical_sha}")
    print(
        "Selection manifest SHA-256 (final on-disk bytes): "
        f"{published_manifest_sha256}"
    )
    for window in windows:
        print(
            f"window {window['window_number']}: "
            f"[{window['start_index']}, {window['end_index_exclusive']}) "
            f"{window['first_utc']} .. {window['last_utc']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

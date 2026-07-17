#!/usr/bin/env python3
"""Prepare immutable real XAUUSD H1 data and a 12-chart human label pack.

Example:
    python scripts/prepare_xauusd_h1_benchmark.py \
        --input ~/Downloads/XAUUSD_H1.csv \
        --source WEALTHTEX_MT5
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared.types.models import Timeframe
from swing_engine.annotations import write_human_annotation_template
from swing_engine.benchmark_data import canonicalise_csv, load_candles_csv
from swing_engine.benchmark_sampling import select_calibration_windows

REPO_ROOT = Path(__file__).resolve().parents[1]
BENCHMARKS_ROOT = REPO_ROOT / "benchmarks"
DEFAULT_DATA = BENCHMARKS_ROOT / "data" / "real" / "XAUUSD" / "H1" / "XAUUSD_H1.real.csv.gz"
DEFAULT_LABELS = BENCHMARKS_ROOT / "labels" / "XAUUSD_H1.human.json"
DEFAULT_MANIFEST = BENCHMARKS_ROOT / "datasets" / "XAUUSD_H1.human.manifest.json"


def _relative(path: Path, base: Path) -> str:
    return Path(os.path.relpath(path.resolve(), base.resolve())).as_posix()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Canonicalise real XAUUSD H1 data and build the first human annotation pack"
    )
    parser.add_argument("--input", required=True, type=Path, help="MT5/vendor CSV export")
    parser.add_argument("--source", default="BROKER_EXPORT", help="Feed/vendor identity")
    parser.add_argument("--price-basis", default="MID", choices=["MID", "BID", "ASK"])
    parser.add_argument("--source-timezone", default="UTC", help="IANA timezone for naive broker timestamps, e.g. Europe/Helsinki")
    parser.add_argument("--output-data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--window-size", type=int, default=400)
    parser.add_argument("--left-context", type=int, default=50)
    parser.add_argument("--right-context", type=int, default=50)
    parser.add_argument("--stride", type=int, default=48)
    parser.add_argument("--per-regime", type=int, default=2)
    args = parser.parse_args()

    output, checksum, count = canonicalise_csv(
        args.input,
        args.output_data,
        symbol="XAUUSD",
        timeframe=Timeframe.H1,
        source=args.source,
        price_basis=args.price_basis,
        source_timezone=args.source_timezone,
    )
    candles = load_candles_csv(
        output,
        symbol="XAUUSD",
        timeframe=Timeframe.H1,
        expected_sha256=checksum,
    )
    windows = select_calibration_windows(
        candles,
        symbol="XAUUSD",
        timeframe="H1",
        window_size=args.window_size,
        left_context=args.left_context,
        right_context=args.right_context,
        stride=args.stride,
        per_regime=args.per_regime,
        split="TRAIN",
    )

    dataset_id = "XAUUSD_H1_REAL_V1"
    label_data_path = _relative(output, args.labels.parent)
    write_human_annotation_template(
        args.labels,
        dataset_id=dataset_id,
        symbol="XAUUSD",
        timeframe="H1",
        data_file=label_data_path,
        data_sha256=checksum,
        candles=candles,
        windows=windows,
        source=args.source,
        price_basis=args.price_basis,
    )

    manifest_data_path = _relative(output, BENCHMARKS_ROOT)
    datasets = []
    for window in windows:
        datasets.append(
            {
                "id": window.sample_id,
                "symbol": "XAUUSD",
                "timeframe": "H1",
                "regime": window.primary_regime,
                "bars": window.source_end_index - window.source_start_index + 1,
                "labels_file": _relative(args.labels, BENCHMARKS_ROOT / "labels"),
                "min_f1": 0.0,
                "description": "Real XAUUSD H1 human calibration window",
                "source_type": "file",
                "data_file": manifest_data_path,
                "data_sha256": checksum,
                "source_start_index": window.source_start_index,
                "source_end_index": window.source_end_index,
                "labelable_start_index": window.labelable_start_index,
                "labelable_end_index": window.labelable_end_index,
                "sample_id": window.sample_id,
                "split": window.split,
                "label_origin": "HUMAN_DRAFT",
                "enabled": True,
            }
        )
    payload = {
        "version": "2.0",
        "description": "Real XAUUSD H1 human swing benchmark calibration pack",
        "dataset_id": dataset_id,
        "data_sha256": checksum,
        "status": "DRAFT",
        "datasets": datasets,
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(f"Canonical candles: {output}")
    print(f"Bars:              {count}")
    print(f"SHA-256:           {checksum}")
    print(f"Human labels:      {args.labels}")
    print(f"Sample manifest:   {args.manifest}")
    print(f"Calibration charts:{len(windows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

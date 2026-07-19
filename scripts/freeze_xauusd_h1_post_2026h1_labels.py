#!/usr/bin/env python3
"""Freeze the adjudicated post-2026H1 benchmark package.

Creates one immutable, self-contained package containing:

- canonical UTC candle data;
- frozen human-adjudicated labels;
- a package-relative dataset manifest;
- a cryptographic freeze receipt.

The freezer never runs the swing detector and never loads predictions.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import os
import shutil
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def load_module(
    filename: str,
    module_name: str,
):
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


PASSES = load_module(
    "manage_xauusd_h1_post_2026h1_label_passes.py",
    "fxn_post_2026h1_freeze_passes",
)

ADJUDICATION = load_module(
    "manage_xauusd_h1_post_2026h1_adjudication.py",
    "fxn_post_2026h1_freeze_adjudication",
)

from shared.types.models import Candle, Timeframe  # noqa: E402
from swing_engine.annotations import (  # noqa: E402
    validate_annotation_document,
)
from swing_engine.benchmark_data import (  # noqa: E402
    write_canonical_candles_csv,
)


DATA_FILENAME = (
    "XAUUSD_H1_post_2026H1_locked.real.csv.gz"
)
LABELS_FILENAME = (
    "XAUUSD_H1_post_2026H1_locked.human.json"
)
MANIFEST_FILENAME = (
    "XAUUSD_H1_post_2026H1_locked."
    "human.manifest.json"
)
RECEIPT_FILENAME = "freeze_receipt.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8")
        )
    except FileNotFoundError as exc:
        raise SystemExit(
            f"REFUSED: missing file {path}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(
            f"REFUSED: invalid JSON in {path}: {exc}"
        ) from exc

    if not isinstance(value, dict):
        raise SystemExit(
            f"REFUSED: JSON root must be an object: {path}"
        )

    return value


def resolve_repo_path(value: str) -> Path:
    path = Path(value)

    if path.is_absolute():
        return path

    return (ROOT / path).resolve()


def load_frozen_protocol(
    selection: dict[str, Any],
) -> tuple[dict[str, Any], Path]:
    block = selection.get("protocol")

    if not isinstance(block, dict):
        raise SystemExit(
            "REFUSED: selection manifest has no "
            "frozen protocol reference"
        )

    raw_path = block.get("path")
    expected_hash = block.get("sha256")

    if not isinstance(raw_path, str):
        raise SystemExit(
            "REFUSED: invalid protocol path"
        )

    protocol_path = resolve_repo_path(raw_path)

    if not protocol_path.exists():
        raise SystemExit(
            f"REFUSED: missing protocol {protocol_path}"
        )

    if sha256(protocol_path) != expected_hash:
        raise SystemExit(
            "REFUSED: frozen protocol SHA-256 mismatch"
        )

    protocol = load_json(protocol_path)

    if protocol.get("protocol_id") != (
        selection.get("protocol_id")
    ):
        raise SystemExit(
            "REFUSED: protocol ID does not match "
            "selection manifest"
        )

    labeling = protocol.get("labeling", {})

    if int(labeling.get("passes", 0)) != 2:
        raise SystemExit(
            "REFUSED: frozen protocol does not "
            "require exactly two passes"
        )

    if labeling.get(
        "predictions_visible_to_labeler"
    ) is not False:
        raise SystemExit(
            "REFUSED: predictions were not frozen "
            "as hidden"
        )

    if labeling.get(
        "engine_version_visible_to_labeler"
    ) is not False:
        raise SystemExit(
            "REFUSED: engine version was not frozen "
            "as hidden"
        )

    if labeling.get(
        "conflicts_require_explicit_adjudication"
    ) is not True:
        raise SystemExit(
            "REFUSED: explicit adjudication was not "
            "required by the protocol"
        )

    return protocol, protocol_path


def read_windows(
    selection_root: Path,
    windows: list[dict[str, Any]],
) -> tuple[
    list[Candle],
    dict[int, list[dict[str, str]]],
    list[dict[str, Any]],
]:
    candles: list[Candle] = []
    rows_by_window: dict[
        int,
        list[dict[str, str]],
    ] = {}
    samples: list[dict[str, Any]] = []

    seen_timestamps = set()
    previous_timestamp = None

    for window in windows:
        number = int(window["window_number"])
        path = (
            selection_root
            / str(window["path"])
        )

        if sha256(path) != window["sha256"]:
            raise SystemExit(
                f"REFUSED: window {number} hash mismatch"
            )

        with path.open(
            "r",
            encoding="utf-8-sig",
            newline="",
        ) as handle:
            rows = list(csv.DictReader(handle))

        expected_bars = int(window["bars"])

        if len(rows) != expected_bars:
            raise SystemExit(
                f"REFUSED: window {number} row count "
                "does not match its manifest"
            )

        source_start = len(candles)

        for local_index, row in enumerate(rows):
            if int(
                row["window_bar_index"]
            ) != local_index:
                raise SystemExit(
                    f"REFUSED: window {number} has "
                    "invalid local indexes"
                )

            timestamp = PASSES.parse_utc(
                row["timestamp_utc"],
                field=(
                    f"window {number} "
                    f"timestamp_utc"
                ),
            )

            if timestamp in seen_timestamps:
                raise SystemExit(
                    "REFUSED: selected windows contain "
                    f"duplicate UTC candle {timestamp}"
                )

            if (
                previous_timestamp is not None
                and timestamp <= previous_timestamp
            ):
                raise SystemExit(
                    "REFUSED: selected windows are not "
                    "strictly chronological"
                )

            seen_timestamps.add(timestamp)
            previous_timestamp = timestamp

            candles.append(
                Candle(
                    symbol="XAUUSD",
                    timeframe=Timeframe.H1,
                    timestamp=timestamp,
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=int(row["volume"]),
                    tick_volume=int(
                        row["tick_volume"]
                    ),
                    spread=float(
                        row["spread_price"]
                    ),
                )
            )

        source_end = len(candles) - 1
        sample_id = (
            "XAUUSD_H1_POST_2026H1_"
            f"{number:03d}"
        )

        rows_by_window[number] = rows

        samples.append(
            {
                "sample_id": sample_id,
                "window_number": number,
                "split": "TEST",
                "source_start_index": source_start,
                "source_end_index": source_end,
                "labelable_start_index": 0,
                "labelable_end_index": (
                    expected_bars - 1
                ),
                "bars": expected_bars,
                "start_timestamp": rows[0][
                    "timestamp_utc"
                ],
                "end_timestamp": rows[-1][
                    "timestamp_utc"
                ],
                "window_file": str(
                    window["path"]
                ),
                "window_sha256": str(
                    window["sha256"]
                ),
            }
        )

    return candles, rows_by_window, samples


def build_swings(
    resolved_labels: list[dict[str, Any]],
    *,
    rows_by_window: dict[
        int,
        list[dict[str, str]],
    ],
    samples: list[dict[str, Any]],
    adjudicator_id: str,
) -> list[dict[str, Any]]:
    sample_by_window = {
        int(sample["window_number"]): sample
        for sample in samples
    }

    ordered = sorted(
        resolved_labels,
        key=lambda label: (
            int(label["window_number"]),
            int(label["pivot_index"]),
            str(label["direction"]),
        ),
    )

    swings: list[dict[str, Any]] = []

    for number, label in enumerate(
        ordered,
        start=1,
    ):
        window_number = int(
            label["window_number"]
        )
        pivot_index = int(
            label["pivot_index"]
        )
        confirmation_index = int(
            label["confirmed_at_index"]
        )
        direction = str(label["direction"])
        tier = str(label["tier"])
        scope = str(label["scope"])

        rows = rows_by_window[
            window_number
        ]
        sample = sample_by_window[
            window_number
        ]

        pivot_row = rows[pivot_index]
        confirmation_row = rows[
            confirmation_index
        ]

        price = float(
            pivot_row[
                "high"
                if direction == "HIGH"
                else "low"
            ]
        )

        tags = [
            "HUMAN_ADJUDICATED",
            "BLIND_TWO_PASS",
            "EXPLICIT_ADJUDICATION",
            "CAUSAL_CONFIRMATION",
            (
                "MAJOR_SWING"
                if tier == "MAJOR"
                else "MINOR_SWING"
            ),
            (
                "EXTERNAL_STRUCTURE"
                if scope == "EXTERNAL"
                else "INTERNAL_STRUCTURE"
            ),
        ]

        swings.append(
            {
                "label_id": (
                    "XAUUSD_H1_POST_2026H1_"
                    f"SWG_{number:04d}"
                ),
                "sample_id": sample[
                    "sample_id"
                ],
                "pivot_index": pivot_index,
                "source_bar_index": (
                    int(
                        sample[
                            "source_start_index"
                        ]
                    )
                    + pivot_index
                ),
                "timestamp": pivot_row[
                    "timestamp_utc"
                ],
                "price": price,
                "price_field": direction,
                "direction": direction,
                "tier": tier,
                "scope": scope,
                "confirmation_status": (
                    "ADJUDICATED"
                ),
                "confirmed_at_index": (
                    confirmation_index
                ),
                "confirmed_at_timestamp": (
                    confirmation_row[
                        "timestamp_utc"
                    ]
                ),
                "tags": tags,
                "notes": str(
                    label.get("notes", "")
                ),
                "annotator_id": (
                    adjudicator_id
                ),
                "review_status": (
                    "ADJUDICATED"
                ),
            }
        )

    return swings


def package_relative(
    from_path: Path,
    to_path: Path,
) -> str:
    return os.path.relpath(
        to_path,
        start=from_path.parent,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__
    )

    parser.add_argument(
        "--selection-root",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--pass-one",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--pass-two",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--comparison",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--adjudication",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--frozen-at",
        help=(
            "Optional explicit ISO-8601 UTC "
            "timestamp."
        ),
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    selection_root = (
        args.selection_root.resolve()
    )
    output_root = args.output_root.resolve()
    staging_root = output_root.with_name(
        f".staging-{output_root.name}"
    )

    if output_root.exists():
        raise SystemExit(
            "REFUSED: immutable frozen benchmark "
            f"already exists: {output_root}"
        )

    if staging_root.exists():
        raise SystemExit(
            "REFUSED: stale staging directory "
            f"exists: {staging_root}"
        )

    (
        selection,
        selection_manifest_path,
        windows,
    ) = PASSES.load_selection(
        selection_root
    )

    protocol, protocol_path = (
        load_frozen_protocol(selection)
    )

    adjudication_path = (
        args.adjudication.resolve()
    )
    adjudication_document = load_json(
        adjudication_path
    )

    adjudicated = (
        ADJUDICATION.validate_document(
            adjudication_document,
            selection_root=selection_root,
            pass_one_path=(
                args.pass_one.resolve()
            ),
            pass_two_path=(
                args.pass_two.resolve()
            ),
            comparison_path=(
                args.comparison.resolve()
            ),
        )
    )

    if adjudicated["status"] != "COMPLETE":
        raise SystemExit(
            "REFUSED: adjudication must be COMPLETE"
        )

    if not adjudicated[
        "resolved_labels"
    ]:
        raise SystemExit(
            "REFUSED: adjudication produced no "
            "final labels"
        )

    frozen_at = (
        PASSES.parse_utc(
            args.frozen_at,
            field="--frozen-at",
        )
        if args.frozen_at
        else datetime.now(timezone.utc)
    )

    candles, rows_by_window, samples = (
        read_windows(
            selection_root,
            windows,
        )
    )

    swings = build_swings(
        adjudicated["resolved_labels"],
        rows_by_window=rows_by_window,
        samples=samples,
        adjudicator_id=adjudicated[
            "adjudicator_id"
        ],
    )

    dataset_id = selection["protocol_id"]
    output_root.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    staging_root.mkdir()

    try:
        data_path = (
            staging_root / DATA_FILENAME
        )
        labels_path = (
            staging_root / LABELS_FILENAME
        )
        manifest_path = (
            staging_root / MANIFEST_FILENAME
        )
        receipt_path = (
            staging_root / RECEIPT_FILENAME
        )

        write_canonical_candles_csv(
            data_path,
            candles,
            source=(
                "MT5_XAUUSD_VX_POST_2026H1_"
                "LOCKED_WINDOWS"
            ),
            price_basis="MID",
        )

        data_sha = sha256(data_path)

        labels_document = {
            "benchmark_id": dataset_id,
            "benchmark_version": (
                "1.0.0-locked-human-adjudicated"
            ),
            "label_policy_version": (
                protocol["protocol_id"]
            ),
            "label_origin": (
                "HUMAN_ADJUDICATED"
            ),
            "status": (
                "FROZEN_HUMAN_ADJUDICATED"
            ),
            "dataset": {
                "dataset_id": dataset_id,
                "symbol": "XAUUSD",
                "timeframe": "H1",
                "timezone": "UTC",
                "price_basis": "MID",
                "source": (
                    "MT5_XAUUSD_VX_POST_2026H1_"
                    "LOCKED_WINDOWS"
                ),
                "data_file": package_relative(
                    labels_path,
                    data_path,
                ),
                "data_sha256": data_sha,
                "bar_count": len(candles),
                "first_timestamp": (
                    candles[0]
                    .timestamp
                    .isoformat()
                ),
                "last_timestamp": (
                    candles[-1]
                    .timestamp
                    .isoformat()
                ),
            },
            "samples": samples,
            "swings": swings,
            "review": {
                "required_annotators": 2,
                "adjudicator": adjudicated[
                    "adjudicator_id"
                ],
                "adjudicated_at": (
                    PASSES.utc_text(
                        adjudicated[
                            "completed_at"
                        ]
                    )
                ),
                "label_frozen_at": (
                    PASSES.utc_text(
                        frozen_at
                    )
                ),
                "prediction_visibility": (
                    "HIDDEN_UNTIL_LABEL_FREEZE"
                ),
                "engine_version_visibility": (
                    "HIDDEN_UNTIL_LABEL_FREEZE"
                ),
                "pass_1_sha256": (
                    adjudicated[
                        "pass_1"
                    ]["sha256"]
                ),
                "pass_2_sha256": (
                    adjudicated[
                        "pass_2"
                    ]["sha256"]
                ),
                "comparison_sha256": (
                    PASSES.sha256(
                        args.comparison.resolve()
                    )
                ),
                "adjudication_sha256": (
                    PASSES.sha256(
                        adjudication_path
                    )
                ),
                "notes": (
                    "Two blind labeling passes, "
                    "minimum-delay enforcement, and "
                    "explicit human adjudication. "
                    "No predictions were visible "
                    "before label freeze."
                ),
            },
        }

        labels_path.write_text(
            json.dumps(
                labels_document,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        issues = validate_annotation_document(
            labels_path
        )

        errors = [
            issue
            for issue in issues
            if issue.severity == "ERROR"
        ]

        if errors:
            details = "\n- ".join(
                (
                    f"{issue.code}: "
                    f"{issue.message}"
                )
                for issue in errors
            )

            raise SystemExit(
                "REFUSED: frozen label validation "
                f"failed:\n- {details}"
            )

        labels_sha = sha256(labels_path)

        labels_by_sample = Counter(
            swing["sample_id"]
            for swing in swings
        )

        datasets = []

        for sample in samples:
            datasets.append(
                {
                    "id": sample["sample_id"],
                    "sample_id": (
                        sample["sample_id"]
                    ),
                    "symbol": "XAUUSD",
                    "timeframe": "H1",
                    "regime": "unknown",
                    "bars": sample["bars"],
                    "labels_file": (
                        LABELS_FILENAME
                    ),
                    "human_review": True,
                    "label_source": (
                        "HUMAN_ADJUDICATED"
                    ),
                    "evaluation_tolerance_bars": 0,
                    "description": (
                        "Frozen post-2026H1 "
                        "human-adjudicated TEST window"
                    ),
                    "source_type": "real",
                    "data_file": DATA_FILENAME,
                    "data_sha256": data_sha,
                    "source_start_index": (
                        sample[
                            "source_start_index"
                        ]
                    ),
                    "source_end_index": (
                        sample[
                            "source_end_index"
                        ]
                    ),
                    "labelable_start_index": (
                        sample[
                            "labelable_start_index"
                        ]
                    ),
                    "labelable_end_index": (
                        sample[
                            "labelable_end_index"
                        ]
                    ),
                    "split": "TEST",
                    "label_origin": (
                        "HUMAN_ADJUDICATED"
                    ),
                    "enabled": True,
                }
            )

        manifest_document = {
            "manifest_version": "1.0",
            "dataset_id": dataset_id,
            "protocol_id": (
                protocol["protocol_id"]
            ),
            "status": (
                "FROZEN_UNBLINDED_LABELS_"
                "NOT_EVALUATED"
            ),
            "path_resolution": (
                "PACKAGE_RELATIVE"
            ),
            "generated_at_utc": (
                PASSES.utc_text(
                    frozen_at
                )
            ),
            "candidate": protocol[
                "candidate"
            ],
            "baseline": protocol[
                "baseline"
            ],
            "files": {
                "data": {
                    "path": DATA_FILENAME,
                    "sha256": data_sha,
                },
                "labels": {
                    "path": LABELS_FILENAME,
                    "sha256": labels_sha,
                },
            },
            "datasets": datasets,
            "contamination_controls": {
                "predictions_loaded": False,
                "swing_detector_executed": False,
                "candidate_evaluated": False,
                "baseline_evaluated": False,
            },
        }

        manifest_path.write_text(
            json.dumps(
                manifest_document,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        manifest_sha = sha256(
            manifest_path
        )

        receipt = {
            "dataset_id": dataset_id,
            "protocol_id": (
                protocol["protocol_id"]
            ),
            "status": (
                "FROZEN_HUMAN_ADJUDICATED_"
                "NOT_EVALUATED"
            ),
            "frozen_at_utc": (
                PASSES.utc_text(
                    frozen_at
                )
            ),
            "candidate": protocol[
                "candidate"
            ],
            "baseline": protocol[
                "baseline"
            ],
            "counts": {
                "windows": len(samples),
                "bars": len(candles),
                "labels": len(swings),
                "labels_by_sample": dict(
                    sorted(
                        labels_by_sample.items()
                    )
                ),
            },
            "source_evidence": {
                "protocol": {
                    "path": (
                        PASSES.display_path(
                            protocol_path
                        )
                    ),
                    "sha256": sha256(
                        protocol_path
                    ),
                },
                "selection_manifest": {
                    "path": (
                        PASSES.display_path(
                            selection_manifest_path
                        )
                    ),
                    "sha256": sha256(
                        selection_manifest_path
                    ),
                },
                "pass_1_sha256": (
                    adjudicated[
                        "pass_1"
                    ]["sha256"]
                ),
                "pass_2_sha256": (
                    adjudicated[
                        "pass_2"
                    ]["sha256"]
                ),
                "comparison_sha256": (
                    PASSES.sha256(
                        args.comparison.resolve()
                    )
                ),
                "adjudication_sha256": (
                    PASSES.sha256(
                        adjudication_path
                    )
                ),
            },
            "outputs": {
                "data_sha256": data_sha,
                "labels_sha256": labels_sha,
                "manifest_sha256": (
                    manifest_sha
                ),
            },
            "validation": {
                "annotation_errors": 0,
                "annotation_warnings": sum(
                    issue.severity == "WARNING"
                    for issue in issues
                ),
            },
            "policy": {
                "predictions_loaded": False,
                "swing_detector_executed": False,
                "candidate_evaluated": False,
                "baseline_evaluated": False,
                "evaluation_allowed_after_freeze": (
                    True
                ),
            },
        }

        receipt_path.write_text(
            json.dumps(
                receipt,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        staging_root.replace(
            output_root
        )

    except BaseException:
        if staging_root.exists():
            shutil.rmtree(staging_root)

        raise

    print()
    print("POST-2026H1 LABEL FREEZE COMPLETE")
    print("=" * 76)
    print("Output:", output_root)
    print("Windows:", len(samples))
    print("Bars:", len(candles))
    print("Labels:", len(swings))
    print("Data SHA-256:", data_sha)
    print("Labels SHA-256:", labels_sha)
    print("Manifest SHA-256:", manifest_sha)
    print(
        "Annotation warnings:",
        receipt["validation"][
            "annotation_warnings"
        ],
    )
    print()
    print(
        "No predictions were loaded and no "
        "swing detector was executed."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

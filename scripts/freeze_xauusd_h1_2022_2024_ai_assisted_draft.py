#!/usr/bin/env python3
"""Freeze AI-assisted engineering-draft labels for retrospective windows.

Classification: AI_ASSISTED_ENGINEERING_DIAGNOSTIC

This freezer:
- imports no swing detection / candidate / baseline evaluation code
- never modifies pass_1.json or locked human retrospective artifacts
- publishes an immutable engineering package under benchmarks/data/engineering/

These labels remain permanently AI_ASSISTED_ENGINEERING_DRAFT and are never a
human blind pass, release gate, or production certification evidence.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shared.types.models import Candle, Timeframe  # noqa: E402
from swing_engine.annotations import validate_annotation_document  # noqa: E402
from swing_engine.benchmark_data import write_canonical_candles_csv  # noqa: E402


DATA_FILENAME = "XAUUSD_H1_2022_2024_ai_draft.real.csv.gz"
LABELS_FILENAME = "XAUUSD_H1_2022_2024_ai_draft.labels.json"
MANIFEST_FILENAME = "XAUUSD_H1_2022_2024_ai_draft.manifest.json"
RECEIPT_FILENAME = "freeze_receipt.json"

DATASET_ID = "XAUUSD_H1_2022_2024_AI_ASSISTED_ENGINEERING_DRAFT_V1"
PROTOCOL_ID = "XAUUSD_H1_2022_2024_RETROSPECTIVE_LOCKED_V1"

# Local AI-diagnostic constants (do not alter global annotation policy).
AI_DRAFT_ORIGIN = "AI_ASSISTED_ENGINEERING_DRAFT"
AI_DIAGNOSTIC_TYPE = "AI_ASSISTED_ENGINEERING_DIAGNOSTIC"
AI_DRAFT_STATUS = "FROZEN_AI_ASSISTED_ENGINEERING_DRAFT_NOT_EVALUATED"

# Compatibility aliases used by package writers/tests.
BENCHMARK_TYPE = AI_DIAGNOSTIC_TYPE
LABEL_ORIGIN = AI_DRAFT_ORIGIN
PACKAGE_STATUS = AI_DRAFT_STATUS

REFUSED_LABEL_ORIGINS = frozenset(
    {
        "HUMAN",
        "HUMAN_DRAFT",
        "HUMAN_ADJUDICATED",
        "AI_ASSISTED_EXPERT_DRAFT",
    }
)

EXPECTED_SELECTION_SHA = (
    "9bdaa635b71b09287def03bd38a0a8fe3c1a50a5f0fd431ee686e685bbc369e8"
)
EXPECTED_PASS1_SHA = (
    "d1fe3440c0cc21eb888a07caadeb6893830c0354b7341b8157a64debca1bd0ca"
)
EXPECTED_WINDOW_COUNTS = {1: 4, 2: 8, 3: 4, 4: 9, 5: 6, 6: 11}
EXPECTED_TOTAL = 42

ALLOWED_TIER_SCOPE = {
    ("MAJOR", "EXTERNAL"),
    ("MAJOR", "INTERNAL"),
    ("MINOR", "INTERNAL"),
}

DIAGNOSTIC_WARNING = (
    "These metrics use AI-assisted engineering-draft labels. They are diagnostic "
    "only and cannot establish human benchmark performance, release approval, or "
    "production certification."
)

DRAFT_REQUIRED_FILES = (
    "ai_assisted_labels.json",
    "methodology.json",
    "review.md",
    *(f"annotated_window_{i:02d}.svg" for i in range(1, 7)),
)


class FreezeError(SystemExit):
    """Fail-closed refusal."""


def refuse_non_ai_draft_origin(value: Any, *, field: str) -> str:
    """Local AI-draft origin gate; independent of PROTECTED_ANNOTATION_ORIGINS."""
    if value is None or (isinstance(value, str) and not value.strip()):
        raise FreezeError(f"REFUSED: missing {field}")
    origin = str(value)
    if origin in REFUSED_LABEL_ORIGINS:
        raise FreezeError(
            f"REFUSED: {field} {origin!r} is forbidden for AI engineering draft"
        )
    if origin != AI_DRAFT_ORIGIN:
        raise FreezeError(
            f"REFUSED: {field} must be exactly {AI_DRAFT_ORIGIN}, got {origin!r}"
        )
    return origin


def refuse_non_diagnostic_eligibility(
    eligibility: dict[str, Any] | None,
    *,
    field: str = "eligibility",
) -> None:
    eligibility = eligibility or {}
    for key in (
        "eligible_for_human_benchmark",
        "human_adjudicated",
        "eligible_for_release_gate",
        "eligible_for_production_certification",
        "eligible_for_tuning",
        "prospective_test",
    ):
        if eligibility.get(key) is not False:
            raise FreezeError(f"REFUSED: {field}.{key} must be false")
    if eligibility.get("eligible_for_engineering_diagnostic") is not True:
        raise FreezeError(
            f"REFUSED: {field}.eligible_for_engineering_diagnostic must be true"
        )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise FreezeError(f"REFUSED: JSON object required: {path}")
    return value


def parse_utc(value: str, *, field: str) -> datetime:
    raw = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise FreezeError(f"REFUSED: invalid {field}: {value!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def package_relative(from_path: Path, to_path: Path) -> str:
    return os.path.relpath(to_path, start=from_path.parent)


def confidence_to_float(value: str) -> float:
    if value == "HIGH":
        return 0.88
    if value == "MEDIUM":
        return 0.75
    raise FreezeError(f"REFUSED: unsupported confidence {value!r}")


def validate_draft_inputs(
    draft_root: Path,
    selection_root: Path,
) -> dict[str, Any]:
    draft_root = draft_root.resolve()
    selection_root = selection_root.resolve()

    missing = [name for name in DRAFT_REQUIRED_FILES if not (draft_root / name).exists()]
    if missing:
        raise FreezeError(
            "REFUSED: AI draft missing required files: " + ", ".join(missing)
        )

    input_hashes = {
        name: sha256(draft_root / name) for name in DRAFT_REQUIRED_FILES
    }

    labels_doc = load_json(draft_root / "ai_assisted_labels.json")
    methodology = load_json(draft_root / "methodology.json")
    review_text = (draft_root / "review.md").read_text(encoding="utf-8")

    refuse_non_ai_draft_origin(labels_doc.get("origin"), field="draft.origin")
    if labels_doc.get("eligible_for_human_benchmark") is not False:
        raise FreezeError("REFUSED: draft must set eligible_for_human_benchmark=false")
    if methodology.get("classification") != LABEL_ORIGIN:
        raise FreezeError("REFUSED: methodology classification mismatch")
    if "AI_ASSISTED" not in review_text and "AI-assisted" not in review_text:
        raise FreezeError("REFUSED: review.md does not identify AI-assisted work")

    flat = labels_doc.get("labels")
    if not isinstance(flat, list):
        raise FreezeError("REFUSED: draft labels list missing")

    reported_total = labels_doc.get("label_count_total")
    reported_by_window = labels_doc.get("label_count_by_window") or {}
    if reported_total != len(flat):
        raise FreezeError(
            "REFUSED: label_count_total disagrees with labels list length"
        )

    counts: dict[int, int] = {i: 0 for i in range(1, 7)}
    for lab in flat:
        wi = int(lab["window_number"])
        if wi not in counts:
            raise FreezeError(f"REFUSED: window_number out of range: {wi}")
        counts[wi] += 1

    for wi, expected in EXPECTED_WINDOW_COUNTS.items():
        reported = int(reported_by_window.get(str(wi), reported_by_window.get(wi, -1)))
        if counts[wi] != expected or reported != expected:
            raise FreezeError(
                "REFUSED: window label counts disagree with expected report "
                f"(window {wi}: found={counts[wi]}, reported={reported}, "
                f"expected={expected})"
            )
    if len(flat) != EXPECTED_TOTAL or reported_total != EXPECTED_TOTAL:
        raise FreezeError(
            f"REFUSED: total label count {len(flat)}/{reported_total} "
            f"!= expected {EXPECTED_TOTAL}"
        )

    selection_path = selection_root / "selection_manifest.json"
    if not selection_path.exists():
        raise FreezeError(f"REFUSED: missing selection manifest {selection_path}")
    selection_sha = sha256(selection_path)
    if selection_sha != EXPECTED_SELECTION_SHA:
        raise FreezeError(
            "REFUSED: selection manifest SHA-256 mismatch\n"
            f"Expected: {EXPECTED_SELECTION_SHA}\n"
            f"Actual:   {selection_sha}"
        )
    selection = load_json(selection_path)
    windows = selection.get("windows")
    if not isinstance(windows, list) or len(windows) != 6:
        raise FreezeError("REFUSED: selection must contain exactly six windows")

    rows_by_window: dict[int, list[dict[str, str]]] = {}
    window_hashes: dict[str, str] = {}
    for window in windows:
        number = int(window["window_number"])
        fname = str(window["file"])
        path = selection_root / fname
        digest = sha256(path)
        if digest != window["sha256"]:
            raise FreezeError(f"REFUSED: window {number} hash mismatch vs selection")
        window_hashes[fname] = digest
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        if len(rows) != 192:
            raise FreezeError(f"REFUSED: window {number} must contain 192 bars")
        rows_by_window[number] = rows

    ids: set[str] = set()
    by_window: dict[int, list[dict[str, Any]]] = {i: [] for i in range(1, 7)}
    for lab in flat:
        refuse_non_ai_draft_origin(lab.get("origin"), field=f"label[{lab.get('label_id')}].origin")
        if lab.get("eligible_for_human_benchmark") is not False:
            raise FreezeError("REFUSED: label eligible_for_human_benchmark must be false")

        label_id = str(lab["label_id"])
        if label_id in ids:
            raise FreezeError(f"REFUSED: duplicate label_id {label_id}")
        ids.add(label_id)

        wi = int(lab["window_number"])
        pivot = int(lab["pivot_index"])
        conf = int(lab["confirmed_at_index"])
        if not (0 <= pivot <= 191) or not (0 <= conf <= 191):
            raise FreezeError(f"REFUSED: index out of range for {label_id}")
        if conf <= pivot:
            raise FreezeError(f"REFUSED: confirmation order for {label_id}")

        direction = str(lab["direction"])
        tier = str(lab["tier"])
        scope = str(lab["scope"])
        if (tier, scope) not in ALLOWED_TIER_SCOPE:
            raise FreezeError(f"REFUSED: illegal tier/scope for {label_id}")
        confidence = str(lab["confidence"])
        if confidence not in {"HIGH", "MEDIUM"}:
            raise FreezeError(f"REFUSED: confidence must be HIGH/MEDIUM for {label_id}")
        if confidence == "LOW":
            raise FreezeError(f"REFUSED: LOW confidence labels are forbidden ({label_id})")

        row = rows_by_window[wi][pivot]
        conf_row = rows_by_window[wi][conf]
        if lab["timestamp_utc"] != row["timestamp_utc"]:
            raise FreezeError(f"REFUSED: timestamp mismatch for {label_id}")
        if lab["confirmed_at_timestamp"] != conf_row["timestamp_utc"]:
            raise FreezeError(f"REFUSED: confirmation timestamp mismatch for {label_id}")

        if direction == "HIGH":
            field = "high"
            if lab.get("price_field") != "high":
                raise FreezeError(f"REFUSED: HIGH price_field mismatch for {label_id}")
        elif direction == "LOW":
            field = "low"
            if lab.get("price_field") != "low":
                raise FreezeError(f"REFUSED: LOW price_field mismatch for {label_id}")
        else:
            raise FreezeError(f"REFUSED: invalid direction for {label_id}")

        if Decimal(str(lab["price"])) != Decimal(row[field]):
            raise FreezeError(f"REFUSED: price mismatch for {label_id}")

        by_window[wi].append(lab)

    for wi, labs in by_window.items():
        ordered = sorted(labs, key=lambda item: int(item["pivot_index"]))
        if [int(x["pivot_index"]) for x in labs] != [
            int(x["pivot_index"]) for x in ordered
        ]:
            raise FreezeError(f"REFUSED: labels not chronological in window {wi}")
        directions = [str(x["direction"]) for x in ordered]
        for left, right in zip(directions, directions[1:]):
            if left == right:
                raise FreezeError(
                    f"REFUSED: directions do not alternate in window {wi}"
                )

    pass1 = (
        ROOT
        / "benchmarks/data/locked/XAUUSD/H1/retrospective_2022_2024/labels/pass_1.json"
    )
    if pass1.exists():
        pass1_sha = sha256(pass1)
        if pass1_sha != EXPECTED_PASS1_SHA:
            raise FreezeError(
                "REFUSED: pass_1.json SHA-256 changed\n"
                f"Expected: {EXPECTED_PASS1_SHA}\n"
                f"Actual:   {pass1_sha}"
            )

    return {
        "draft_root": draft_root,
        "selection_root": selection_root,
        "selection_path": selection_path,
        "selection": selection,
        "selection_sha": selection_sha,
        "labels_doc": labels_doc,
        "methodology": methodology,
        "review_text": review_text,
        "input_hashes": input_hashes,
        "rows_by_window": rows_by_window,
        "windows": windows,
        "window_hashes": window_hashes,
        "counts": counts,
        "flat_labels": flat,
        "pass1_sha": EXPECTED_PASS1_SHA if pass1.exists() else None,
    }


def read_concatenated_windows(
    selection_root: Path,
    windows: list[dict[str, Any]],
) -> tuple[list[Candle], list[dict[str, Any]]]:
    candles: list[Candle] = []
    samples: list[dict[str, Any]] = []
    previous: datetime | None = None

    for window in windows:
        number = int(window["window_number"])
        path = selection_root / str(window["file"])
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        source_start = len(candles)
        for local_index, row in enumerate(rows):
            if int(row["window_bar_index"]) != local_index:
                raise FreezeError(
                    f"REFUSED: window {number} has invalid window_bar_index"
                )
            ts = parse_utc(row["timestamp_utc"], field=f"window {number} timestamp")
            if previous is not None and ts <= previous:
                raise FreezeError(
                    "REFUSED: concatenated windows are not chronological"
                )
            previous = ts
            spread_raw = row.get("mean_spread") or row.get("spread_price") or "0"
            candles.append(
                Candle(
                    symbol="XAUUSD",
                    timeframe=Timeframe.H1,
                    timestamp=ts,
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=int(float(row["volume"] or 0)),
                    tick_volume=int(float(row["tick_volume"] or 0)),
                    spread=float(spread_raw),
                )
            )
        source_end = len(candles) - 1
        sample_id = f"XAUUSD_H1_AI_DRAFT_{number:03d}"
        samples.append(
            {
                "sample_id": sample_id,
                "window_number": number,
                "split": "TEST",
                "source_start_index": source_start,
                "source_end_index": source_end,
                "labelable_start_index": 0,
                "labelable_end_index": len(rows) - 1,
                "bars": len(rows),
                "start_timestamp": candles[source_start].timestamp.isoformat(),
                "end_timestamp": candles[source_end].timestamp.isoformat(),
                "window_file": str(window["file"]),
                "window_sha256": str(window["sha256"]),
                "source_global_start_index": int(window["start_index"]),
                "source_global_end_index_exclusive": int(
                    window["end_index_exclusive"]
                ),
            }
        )
    return candles, samples


def build_swings(
    flat_labels: list[dict[str, Any]],
    *,
    rows_by_window: dict[int, list[dict[str, str]]],
    samples: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    sample_by_window = {
        int(sample["window_number"]): sample for sample in samples
    }
    ordered = sorted(
        flat_labels,
        key=lambda lab: (int(lab["window_number"]), int(lab["pivot_index"])),
    )
    swings: list[dict[str, Any]] = []
    for seq, lab in enumerate(ordered, start=1):
        wi = int(lab["window_number"])
        pivot = int(lab["pivot_index"])
        conf = int(lab["confirmed_at_index"])
        direction = str(lab["direction"])
        sample = sample_by_window[wi]
        pivot_row = rows_by_window[wi][pivot]
        conf_row = rows_by_window[wi][conf]
        price = float(pivot_row["high" if direction == "HIGH" else "low"])
        categorical = str(lab["confidence"])
        swings.append(
            {
                "label_id": str(lab["label_id"]),
                "sample_id": sample["sample_id"],
                "pivot_index": pivot,
                "source_bar_index": int(sample["source_start_index"]) + pivot,
                "timestamp": parse_utc(
                    pivot_row["timestamp_utc"], field="pivot timestamp"
                ).isoformat(),
                "price": price,
                "price_field": direction,
                "direction": direction,
                "tier": str(lab["tier"]),
                "scope": str(lab["scope"]),
                "confirmation_status": "CONFIRMED",
                "confirmed_at_index": conf,
                "confirmed_at_timestamp": parse_utc(
                    conf_row["timestamp_utc"], field="confirmation timestamp"
                ).isoformat(),
                "strength": 4 if lab["tier"] == "MAJOR" else 3,
                "quality_score": 85.0 if categorical == "HIGH" else 78.0,
                "confidence": confidence_to_float(categorical),
                "tags": [
                    "AI_ASSISTED_ENGINEERING_DRAFT",
                    "ENGINEERING_DIAGNOSTIC_ONLY",
                    "NOT_HUMAN_ADJUDICATED",
                    "NOT_RELEASE_GATE",
                    "CAUSAL_CONFIRMATION",
                    "MAJOR_SWING" if lab["tier"] == "MAJOR" else "MINOR_SWING",
                    (
                        "EXTERNAL_STRUCTURE"
                        if lab["scope"] == "EXTERNAL"
                        else "INTERNAL_STRUCTURE"
                    ),
                    f"DRAFT_CONFIDENCE_{categorical}",
                ],
                "notes": str(lab.get("notes", "")),
                "annotator_id": "ASSISTANT_ENGINEERING_DRAFT",
                "review_status": "AI_DRAFT",
                "draft_sequence": seq,
                "draft_confidence_category": categorical,
            }
        )
    return swings


def write_readme(path: Path) -> None:
    path.write_text(
        "# XAUUSD H1 2022–2024 AI-assisted engineering draft\n\n"
        "Classification: `AI_ASSISTED_ENGINEERING_DIAGNOSTIC`\n\n"
        "Label origin: `AI_ASSISTED_ENGINEERING_DRAFT`\n\n"
        "Status: `FROZEN_AI_ASSISTED_ENGINEERING_DRAFT_NOT_EVALUATED`\n\n"
        "## Warning\n\n"
        f"{DIAGNOSTIC_WARNING}\n\n"
        "These labels are **not**:\n\n"
        "- HUMAN_ADJUDICATED\n"
        "- an independent blind human pass\n"
        "- a retrospective release benchmark\n"
        "- a prospective benchmark\n"
        "- production certification evidence\n\n"
        "Moon has viewed these proposals and cannot complete `MOON_PASS_1` as an "
        "independent blind annotator. A future human benchmark requires a different "
        "genuinely blind human and a fresh template.\n\n"
        "Do not copy these labels into `pass_1.json`.\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draft-root", type=Path, required=True)
    parser.add_argument("--selection-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--frozen-at", type=str, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    draft_root = args.draft_root.resolve()
    selection_root = args.selection_root.resolve()
    output_root = args.output_root.resolve()
    staging_root = output_root.with_name(f".staging-{output_root.name}")

    if output_root.exists():
        raise FreezeError(
            f"REFUSED: immutable frozen package already exists: {output_root}"
        )
    if staging_root.exists():
        raise FreezeError(
            f"REFUSED: stale staging directory exists: {staging_root}"
        )

    validated = validate_draft_inputs(draft_root, selection_root)
    frozen_at = (
        parse_utc(args.frozen_at, field="--frozen-at")
        if args.frozen_at
        else datetime.now(timezone.utc)
    )

    protocol_path = (
        ROOT
        / "benchmarks/protocols/XAUUSD_H1_2022_2024_retrospective_locked_protocol.json"
    )
    protocol = load_json(protocol_path)
    protocol_sha = sha256(protocol_path)

    candles, samples = read_concatenated_windows(
        selection_root, validated["windows"]
    )
    swings = build_swings(
        validated["flat_labels"],
        rows_by_window=validated["rows_by_window"],
        samples=samples,
    )

    output_root.parent.mkdir(parents=True, exist_ok=True)
    staging_root.mkdir()

    try:
        data_path = staging_root / DATA_FILENAME
        labels_path = staging_root / LABELS_FILENAME
        manifest_path = staging_root / MANIFEST_FILENAME
        receipt_path = staging_root / RECEIPT_FILENAME

        write_canonical_candles_csv(
            data_path,
            candles,
            source="WEALTHTEX_MT5_XAUUSD_VX_RETROSPECTIVE_AI_DRAFT_WINDOWS",
            price_basis="BID",
        )
        data_sha = sha256(data_path)

        labels_document = {
            "benchmark_id": DATASET_ID,
            "benchmark_version": "1.0.0-ai-assisted-engineering-draft",
            "label_policy_version": PROTOCOL_ID,
            "label_origin": LABEL_ORIGIN,
            "status": PACKAGE_STATUS,
            "benchmark_type": BENCHMARK_TYPE,
            "dataset": {
                "dataset_id": DATASET_ID,
                "symbol": "XAUUSD",
                "timeframe": "H1",
                "timezone": "UTC",
                "price_basis": "BID",
                "source": (
                    "WEALTHTEX_MT5_XAUUSD_VX_RETROSPECTIVE_AI_DRAFT_WINDOWS"
                ),
                "data_file": package_relative(labels_path, data_path),
                "data_sha256": data_sha,
                "bar_count": len(candles),
                "first_timestamp": candles[0].timestamp.isoformat(),
                "last_timestamp": candles[-1].timestamp.isoformat(),
            },
            "samples": samples,
            "swings": swings,
            "eligibility": {
                "eligible_for_tuning": False,
                "eligible_for_human_benchmark": False,
                "eligible_for_release_gate": False,
                "eligible_for_production_certification": False,
                "eligible_for_engineering_diagnostic": True,
                "prospective_test": False,
                "human_adjudicated": False,
            },
            "review": {
                "annotator_role": "ASSISTANT_ENGINEERING_DRAFT",
                "label_frozen_at": utc_text(frozen_at),
                "prediction_visibility": "NOT_APPLICABLE_AI_DRAFT",
                "engine_version_visibility": "NOT_APPLICABLE_AI_DRAFT",
                "human_blind_pass_completed": False,
                "moon_blindness_compromised": True,
                "warning": DIAGNOSTIC_WARNING,
                "source_draft_sha256": validated["input_hashes"][
                    "ai_assisted_labels.json"
                ],
            },
            "warning": DIAGNOSTIC_WARNING,
        }
        labels_path.write_text(
            json.dumps(labels_document, indent=2) + "\n",
            encoding="utf-8",
        )
        issues = validate_annotation_document(labels_path)
        errors = [issue for issue in issues if issue.severity == "ERROR"]
        if errors:
            raise FreezeError(
                "REFUSED: annotation validation failed:\n- "
                + "\n- ".join(f"{e.code}: {e.message}" for e in errors)
            )
        labels_sha = sha256(labels_path)

        datasets = []
        for sample in samples:
            datasets.append(
                {
                    "id": sample["sample_id"],
                    "sample_id": sample["sample_id"],
                    "symbol": "XAUUSD",
                    "timeframe": "H1",
                    "regime": "unknown",
                    "bars": sample["bars"],
                    "labels_file": LABELS_FILENAME,
                    "human_review": False,
                    "label_source": LABEL_ORIGIN,
                    "evaluation_tolerance_bars": 0,
                    "description": (
                        "AI-assisted engineering diagnostic TEST window"
                    ),
                    "source_type": "real",
                    "data_file": DATA_FILENAME,
                    "data_sha256": data_sha,
                    "source_start_index": sample["source_start_index"],
                    "source_end_index": sample["source_end_index"],
                    "labelable_start_index": sample["labelable_start_index"],
                    "labelable_end_index": sample["labelable_end_index"],
                    "split": "TEST",
                    "label_origin": LABEL_ORIGIN,
                    "enabled": True,
                }
            )

        manifest = {
            "manifest_version": "1.0",
            "dataset_id": DATASET_ID,
            "protocol_id": PROTOCOL_ID,
            "benchmark_type": BENCHMARK_TYPE,
            "label_origin": LABEL_ORIGIN,
            "status": PACKAGE_STATUS,
            "path_resolution": "PACKAGE_RELATIVE",
            "split": "TEST",
            "generated_at_utc": utc_text(frozen_at),
            "candidate": protocol["candidate"],
            "baseline": protocol["baseline"],
            "eligibility": {
                "eligible_for_tuning": False,
                "eligible_for_human_benchmark": False,
                "eligible_for_release_gate": False,
                "eligible_for_production_certification": False,
                "eligible_for_engineering_diagnostic": True,
                "prospective_test": False,
                "human_adjudicated": False,
            },
            "files": {
                "data": {"path": DATA_FILENAME, "sha256": data_sha},
                "labels": {"path": LABELS_FILENAME, "sha256": labels_sha},
            },
            "datasets": datasets,
            "sample_boundaries": [
                {
                    "sample_id": sample["sample_id"],
                    "window_number": sample["window_number"],
                    "source_start_index": sample["source_start_index"],
                    "source_end_index": sample["source_end_index"],
                    "window_file": sample["window_file"],
                    "window_sha256": sample["window_sha256"],
                    "source_global_start_index": sample[
                        "source_global_start_index"
                    ],
                    "source_global_end_index_exclusive": sample[
                        "source_global_end_index_exclusive"
                    ],
                }
                for sample in samples
            ],
            "contamination_controls": {
                "labels_generated_by_ai": True,
                "human_blind_pass_completed": False,
                "predictions_loaded_during_label_creation": False,
                "swing_engine_executed_during_label_creation": False,
                "predictions_loaded": False,
                "swing_detector_executed": False,
                "candidate_evaluated": False,
                "baseline_evaluated": False,
            },
            "warning": DIAGNOSTIC_WARNING,
        }
        manifest_path.write_text(
            json.dumps(manifest, indent=2) + "\n",
            encoding="utf-8",
        )
        manifest_sha = sha256(manifest_path)

        # Preserve methodology, review, charts byte-for-byte from draft.
        for name in (
            "methodology.json",
            "review.md",
            *(f"annotated_window_{i:02d}.svg" for i in range(1, 7)),
        ):
            src = draft_root / name
            dst = staging_root / name
            dst.write_bytes(src.read_bytes())
            if sha256(dst) != validated["input_hashes"][name]:
                raise FreezeError(f"REFUSED: failed to preserve {name} bytes")

        write_readme(staging_root / "README.md")

        receipt = {
            "dataset_id": DATASET_ID,
            "protocol_id": PROTOCOL_ID,
            "benchmark_type": BENCHMARK_TYPE,
            "label_origin": LABEL_ORIGIN,
            "status": PACKAGE_STATUS,
            "frozen_at_utc": utc_text(frozen_at),
            "candidate": protocol["candidate"],
            "baseline": protocol["baseline"],
            "eligibility": manifest["eligibility"],
            "label_counts": {
                "by_window": {
                    str(k): v for k, v in validated["counts"].items()
                },
                "total": EXPECTED_TOTAL,
            },
            "source_evidence": {
                "selection_manifest": {
                    "path": (
                        str(validated["selection_path"].relative_to(ROOT))
                        if ROOT in validated["selection_path"].parents
                        or validated["selection_path"] == ROOT
                        else str(validated["selection_path"])
                    ),
                    "sha256": validated["selection_sha"],
                },
                "windows": {
                    name: digest
                    for name, digest in validated["window_hashes"].items()
                },
                "protocol": {
                    "path": (
                        str(protocol_path.relative_to(ROOT))
                        if ROOT in protocol_path.parents
                        or protocol_path == ROOT
                        else str(protocol_path)
                    ),
                    "sha256": protocol_sha,
                },
                "pass_1_json": {
                    "path": (
                        "benchmarks/data/locked/XAUUSD/H1/"
                        "retrospective_2022_2024/labels/pass_1.json"
                    ),
                    "sha256": validated["pass1_sha"],
                    "unchanged": True,
                    "note": (
                        "Formal empty human template; AI labels were not "
                        "inserted."
                    ),
                },
                "ai_draft_inputs": validated["input_hashes"],
            },
            "outputs": {
                "data_sha256": data_sha,
                "labels_sha256": labels_sha,
                "manifest_sha256": manifest_sha,
            },
            "contamination_controls": manifest["contamination_controls"],
            "policy": {
                "evaluation_allowed_after_freeze": True,
                "human_benchmark": False,
                "release_gate": False,
                "production_certification": False,
                "engineering_diagnostic_only": True,
            },
            "warning": DIAGNOSTIC_WARNING,
        }
        receipt_path.write_text(
            json.dumps(receipt, indent=2) + "\n",
            encoding="utf-8",
        )

        published = {
            "output_root": str(output_root),
            "status": PACKAGE_STATUS,
            "label_counts": receipt["label_counts"],
            "outputs": receipt["outputs"],
            "warning": DIAGNOSTIC_WARNING,
        }
        staging_root.replace(output_root)
    except Exception:
        if staging_root.exists():
            shutil.rmtree(staging_root)
        raise

    print(json.dumps(published, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

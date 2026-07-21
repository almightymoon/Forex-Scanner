#!/usr/bin/env python3
"""Compatibility adapter for retrospective selection manifests.

The committed retrospective selection_manifest.json uses a native
RETROSPECTIVE_HOLDOUT schema. Shared post-2026H1 labeling helpers expect a
different prospective schema. This module:

- validates the native retrospective schema fail-closed;
- returns an in-memory normalized compatibility view;
- never writes the normalized view to disk;
- never hashes the normalized view;
- always leaves the real selection_manifest.json path as the evidence path so
  downstream documents bind to the committed file-byte SHA-256.
"""

from __future__ import annotations

import csv
import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable


ALGORITHM_VERSION = "PRICE_BLIND_SIX_BUCKET_CENTERED_V1"
BENCHMARK_TYPE = "RETROSPECTIVE_HOLDOUT"
COMPATIBILITY_STATUS = (
    "WINDOWS_SELECTED_UNLABELED_NOT_EVALUATED"
)

RETROSPECTIVE_WINDOW_COLUMNS = {
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
}

REQUIRED_CONTAMINATION_FALSE = (
    "labels_loaded",
    "predictions_loaded",
    "swing_engine_executed",
    "candidate_evaluated",
    "baseline_evaluated",
    "ohlc_inspected_for_selection",
    "selection_uses_prices_or_predictions",
)

REQUIRED_ELIGIBILITY = {
    "eligible_for_labeling": True,
    "eligible_for_evaluation": False,
    "eligible_for_tuning": False,
    "prospective_test": False,
}


class RetrospectiveSelectionError(SystemExit):
    """Fail-closed refusal for retrospective selection adaptation."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RetrospectiveSelectionError(
            f"REFUSED: missing selection manifest {path}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise RetrospectiveSelectionError(
            f"REFUSED: invalid JSON in {path}"
        ) from exc

    if not isinstance(value, dict):
        raise RetrospectiveSelectionError(
            f"REFUSED: selection manifest must be an object: {path}"
        )
    return value


def _fail(errors: list[str]) -> None:
    if errors:
        raise RetrospectiveSelectionError(
            "REFUSED:\n- " + "\n- ".join(errors)
        )


def validate_native_retrospective_manifest(
    manifest: dict[str, Any],
) -> list[str]:
    errors: list[str] = []

    if manifest.get("benchmark_type") != BENCHMARK_TYPE:
        errors.append(
            "benchmark_type must be RETROSPECTIVE_HOLDOUT"
        )

    protocol_id = manifest.get("protocol_id")
    if not isinstance(protocol_id, str) or not protocol_id.strip():
        errors.append("protocol_id must be nonempty")

    if manifest.get("algorithm_version") != ALGORITHM_VERSION:
        errors.append(
            "algorithm_version must be "
            f"{ALGORITHM_VERSION}"
        )

    eligibility = manifest.get("eligibility", {})
    if not isinstance(eligibility, dict):
        errors.append("eligibility must be an object")
        eligibility = {}

    for key, expected in REQUIRED_ELIGIBILITY.items():
        if eligibility.get(key) is not expected:
            errors.append(
                f"eligibility.{key} must be {expected}"
            )

    controls = manifest.get("contamination_controls", {})
    if not isinstance(controls, dict):
        errors.append(
            "contamination_controls must be an object"
        )
        controls = {}

    for key in REQUIRED_CONTAMINATION_FALSE:
        if controls.get(key) is not False:
            errors.append(
                f"contamination_controls.{key} must be false"
            )

    windows = manifest.get("windows")
    if not isinstance(windows, list) or not windows:
        errors.append("windows must be a nonempty list")

    return errors


def normalize_retrospective_manifest(
    native: dict[str, Any],
) -> dict[str, Any]:
    """Build an in-memory prospective-compatible view.

    The returned object is never written to disk and must never be hashed as
    selection evidence. Downstream evidence hashes the committed native file.
    """
    normalized = deepcopy(native)

    windows = []
    for window in native.get("windows", []):
        entry = deepcopy(window)
        if "path" not in entry:
            file_name = entry.get("file")
            if isinstance(file_name, str) and file_name:
                entry["path"] = file_name
        windows.append(entry)
    normalized["windows"] = windows

    window_bars = 0
    if windows:
        try:
            window_bars = int(windows[0].get("bars", 0))
        except (TypeError, ValueError):
            window_bars = 0

    normalized["status"] = COMPATIBILITY_STATUS
    normalized["policy"] = {
        "labels_loaded": False,
        "predictions_loaded": False,
        "swing_engine_imported": False,
        "swing_engine_executed": False,
        "selection_uses_prices": False,
        "selection_uses_predictions": False,
        "selection_uses_chronology_and_indices_only": True,
    }
    normalized["contamination_controls"] = {
        **deepcopy(native.get("contamination_controls", {})),
        "labels_exist": False,
        "predictions_exist": False,
        "swing_engine_executed": False,
        "candidate_evaluated": False,
        "baseline_evaluated": False,
    }
    normalized["selection_parameters"] = {
        "window_bars": window_bars,
        "leading_guard_bars": 48,
        "trailing_guard_bars": 48,
        "bucket_count": len(windows),
        "selection_uses_prices_or_predictions": False,
    }
    normalized["compatibility_adapter"] = {
        "written_to_disk": False,
        "hashes_normalized_view": False,
        "evidence_path_is_native_manifest": True,
        "source_schema": "RETROSPECTIVE_HOLDOUT_NATIVE_V1",
    }
    return normalized


def verify_retrospective_window_file(
    selection_root: Path,
    window: dict[str, Any],
    *,
    parse_utc: Callable[..., Any],
) -> dict[str, Any]:
    errors: list[str] = []

    try:
        number = int(window["window_number"])
        bars = int(window["bars"])
        path_value = str(window.get("path") or window["file"])
        expected_hash = str(window["sha256"])
        expected_first = str(window["first_utc"])
        expected_last = str(window["last_utc"])
    except (KeyError, TypeError, ValueError) as exc:
        raise RetrospectiveSelectionError(
            "REFUSED: malformed window entry in selection manifest"
        ) from exc

    path = selection_root / path_value
    if not path.exists():
        raise RetrospectiveSelectionError(
            f"REFUSED: missing window file {path}"
        )

    actual_hash = sha256_file(path)
    if actual_hash != expected_hash:
        errors.append(f"window {number}: SHA-256 mismatch")

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)

    if set(reader.fieldnames or []) != RETROSPECTIVE_WINDOW_COLUMNS:
        errors.append(
            f"window {number}: unexpected CSV columns"
        )

    if len(rows) != bars:
        errors.append(
            f"window {number}: expected {bars} rows, found {len(rows)}"
        )

    local_indexes: list[int] = []
    global_indexes: list[int] = []

    for line_number, row in enumerate(rows, start=2):
        try:
            local_indexes.append(int(row["window_bar_index"]))
            global_indexes.append(int(row["global_bar_index"]))
            parse_utc(
                row["timestamp_utc"],
                field=(
                    f"window {number} line {line_number} timestamp_utc"
                ),
            )
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(
                f"window {number}: invalid row {line_number}: {exc}"
            )

    if local_indexes != list(range(len(rows))):
        errors.append(
            f"window {number}: local indexes are not contiguous from zero"
        )

    if global_indexes:
        expected_global = list(
            range(
                global_indexes[0],
                global_indexes[0] + len(rows),
            )
        )
        if global_indexes != expected_global:
            errors.append(
                f"window {number}: global indexes are not contiguous"
            )

    if rows:
        if rows[0]["timestamp_utc"] != expected_first:
            errors.append(
                f"window {number}: first timestamp does not match manifest"
            )
        if rows[-1]["timestamp_utc"] != expected_last:
            errors.append(
                f"window {number}: last timestamp does not match manifest"
            )

    _fail(errors)

    return {
        "window_number": number,
        "path": path_value,
        "sha256": actual_hash,
        "bars": bars,
        "first_utc": expected_first,
        "last_utc": expected_last,
    }


def load_retrospective_selection(
    selection_root: Path,
    *,
    parse_utc: Callable[..., Any],
) -> tuple[dict[str, Any], Path, list[dict[str, Any]]]:
    selection_root = selection_root.resolve()
    manifest_path = selection_root / "selection_manifest.json"
    native = load_json(manifest_path)

    _fail(validate_native_retrospective_manifest(native))

    normalized = normalize_retrospective_manifest(native)

    windows = [
        verify_retrospective_window_file(
            selection_root,
            window,
            parse_utc=parse_utc,
        )
        for window in normalized["windows"]
    ]

    numbers = [window["window_number"] for window in windows]
    if numbers != list(range(1, len(windows) + 1)):
        raise RetrospectiveSelectionError(
            "REFUSED: window numbers must be contiguous from one"
        )

    # Critical: return the real on-disk path so sha256(manifest_path) binds to
    # committed bytes, never to an in-memory compatibility object.
    return normalized, manifest_path, windows


def install_on_pass_module(pass_module: Any) -> None:
    """Replace load_selection on a loaded post-2026H1 pass-manager module."""

    def load_selection(selection_root: Path):
        return load_retrospective_selection(
            selection_root,
            parse_utc=pass_module.parse_utc,
        )

    pass_module.load_selection = load_selection


def install_on_module_with_passes(module: Any) -> None:
    """Install adapter onto a module that exposes `.PASSES`."""
    if not hasattr(module, "PASSES"):
        raise RuntimeError(
            "module does not expose PASSES for retrospective adaptation"
        )
    install_on_pass_module(module.PASSES)

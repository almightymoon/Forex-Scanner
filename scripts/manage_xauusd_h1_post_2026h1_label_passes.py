#!/usr/bin/env python3
"""Manage blind labeling passes for the post-2026H1 locked benchmark.

This tool:

- loads only an already-selected immutable window set;
- never imports or executes the swing engine;
- never loads predictions;
- prepares empty blind labeling-pass templates;
- validates manually completed pass documents;
- compares two completed passes without auto-resolving conflicts;
- enforces the frozen minimum delay between labeling passes.

It does not adjudicate or freeze final labels. Those are separate operations.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

PASS_SCHEMA = "XAUUSD_H1_BLIND_LABEL_PASS_V1"
COMPARISON_SCHEMA = "XAUUSD_H1_BLIND_LABEL_COMPARISON_V1"

ALLOWED_DIRECTIONS = {"HIGH", "LOW"}
ALLOWED_TIER_SCOPE = {
    ("MAJOR", "EXTERNAL"),
    ("MAJOR", "INTERNAL"),
    ("MINOR", "INTERNAL"),
}

LABEL_ID_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$"
)

WINDOW_REQUIRED_COLUMNS = {
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
}


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


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_text(value: datetime) -> str:
    return (
        value.astimezone(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def parse_utc(value: str, *, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"{field} must be a non-empty UTC timestamp"
        )

    text = value.strip()

    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(
            f"{field} is not a valid ISO timestamp"
        ) from exc

    if parsed.tzinfo is None:
        raise ValueError(
            f"{field} must include a timezone"
        )

    return parsed.astimezone(timezone.utc)


def fail(errors: list[str]) -> None:
    if not errors:
        return

    raise SystemExit(
        "REFUSED:\n- " + "\n- ".join(errors)
    )


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


def verify_window_file(
    selection_root: Path,
    window: dict[str, Any],
) -> dict[str, Any]:
    errors: list[str] = []

    try:
        number = int(window["window_number"])
        bars = int(window["bars"])
        path_value = str(window["path"])
        expected_hash = str(window["sha256"])
        expected_first = str(window["first_utc"])
        expected_last = str(window["last_utc"])
    except (KeyError, TypeError, ValueError) as exc:
        raise SystemExit(
            "REFUSED: malformed window entry in "
            "selection manifest"
        ) from exc

    path = selection_root / path_value

    if not path.exists():
        raise SystemExit(
            f"REFUSED: missing window file {path}"
        )

    actual_hash = sha256(path)

    if actual_hash != expected_hash:
        errors.append(
            f"window {number}: SHA-256 mismatch"
        )

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)

    if set(reader.fieldnames or []) != (
        WINDOW_REQUIRED_COLUMNS
    ):
        errors.append(
            f"window {number}: unexpected CSV columns"
        )

    if len(rows) != bars:
        errors.append(
            f"window {number}: expected {bars} rows, "
            f"found {len(rows)}"
        )

    local_indexes: list[int] = []
    global_indexes: list[int] = []

    for line_number, row in enumerate(
        rows,
        start=2,
    ):
        try:
            local_indexes.append(
                int(row["window_bar_index"])
            )
            global_indexes.append(
                int(row["global_bar_index"])
            )

            parse_utc(
                row["timestamp_utc"],
                field=(
                    f"window {number} line "
                    f"{line_number} timestamp_utc"
                ),
            )
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(
                f"window {number}: invalid row "
                f"{line_number}: {exc}"
            )

    if local_indexes != list(range(len(rows))):
        errors.append(
            f"window {number}: local indexes are "
            "not contiguous from zero"
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
                f"window {number}: global indexes "
                "are not contiguous"
            )

    if rows:
        if rows[0]["timestamp_utc"] != expected_first:
            errors.append(
                f"window {number}: first timestamp "
                "does not match manifest"
            )

        if rows[-1]["timestamp_utc"] != expected_last:
            errors.append(
                f"window {number}: last timestamp "
                "does not match manifest"
            )

    fail(errors)

    return {
        "window_number": number,
        "path": path_value,
        "sha256": actual_hash,
        "bars": bars,
        "first_utc": expected_first,
        "last_utc": expected_last,
    }


def load_selection(
    selection_root: Path,
) -> tuple[
    dict[str, Any],
    Path,
    list[dict[str, Any]],
]:
    selection_root = selection_root.resolve()
    manifest_path = (
        selection_root
        / "selection_manifest.json"
    )

    manifest = load_json(manifest_path)
    errors: list[str] = []

    if manifest.get("status") != (
        "WINDOWS_SELECTED_UNLABELED_"
        "NOT_EVALUATED"
    ):
        errors.append(
            "selection manifest is not in the "
            "unlabeled, unevaluated state"
        )

    policy = manifest.get("policy", {})
    controls = manifest.get(
        "contamination_controls",
        {},
    )

    forbidden_policy = (
        "labels_loaded",
        "predictions_loaded",
        "swing_engine_imported",
        "swing_engine_executed",
        "selection_uses_prices",
        "selection_uses_predictions",
    )

    for key in forbidden_policy:
        if policy.get(key) is not False:
            errors.append(
                f"selection policy {key} must be false"
            )

    if policy.get(
        "selection_uses_chronology_and_indices_only"
    ) is not True:
        errors.append(
            "selection must use chronology and "
            "indices only"
        )

    forbidden_controls = (
        "labels_exist",
        "predictions_exist",
        "swing_engine_executed",
        "candidate_evaluated",
        "baseline_evaluated",
    )

    for key in forbidden_controls:
        if controls.get(key) is not False:
            errors.append(
                f"contamination control {key} "
                "must be false"
            )

    protocol_id = manifest.get("protocol_id")

    if not isinstance(protocol_id, str) or not (
        protocol_id.strip()
    ):
        errors.append(
            "selection manifest has no protocol_id"
        )

    raw_windows = manifest.get("windows")

    if not isinstance(raw_windows, list) or not (
        raw_windows
    ):
        errors.append(
            "selection manifest contains no windows"
        )

    fail(errors)

    windows = [
        verify_window_file(
            selection_root,
            window,
        )
        for window in raw_windows
    ]

    numbers = [
        window["window_number"]
        for window in windows
    ]

    if numbers != list(
        range(1, len(windows) + 1)
    ):
        raise SystemExit(
            "REFUSED: window numbers must be "
            "contiguous from one"
        )

    return manifest, manifest_path, windows


def labeling_policy(
    selection_manifest: dict[str, Any],
) -> dict[str, Any]:
    parameters = selection_manifest.get(
        "selection_parameters",
        {},
    )

    # The frozen protocol is embedded in the selection manifest
    # through its path and hash. Labeling defaults remain explicit
    # in every pass document.
    return {
        "minimum_days_between_passes": 3,
        "required_passes": 2,
        "conflicts_require_explicit_adjudication": (
            True
        ),
        "window_bars": (
            int(parameters.get("window_bars", 0))
            if parameters.get("window_bars")
            is not None
            else 0
        ),
    }


def build_pass_document(
    *,
    selection_root: Path,
    pass_number: int,
    annotator_id: str,
    created_at: datetime,
) -> dict[str, Any]:
    (
        selection,
        manifest_path,
        windows,
    ) = load_selection(selection_root)

    return {
        "schema_version": PASS_SCHEMA,
        "protocol_id": selection["protocol_id"],
        "selection": {
            "root": display_path(
                selection_root.resolve()
            ),
            "manifest_path": display_path(
                manifest_path
            ),
            "manifest_sha256": sha256(
                manifest_path
            ),
            "status": selection["status"],
        },
        "pass_number": pass_number,
        "annotator_id": annotator_id,
        "status": "DRAFT",
        "created_at_utc": utc_text(created_at),
        "completed_at_utc": None,
        "blindness": {
            "predictions_visible": False,
            "engine_version_visible": False,
            "prior_pass_visible": False,
            "comparison_visible": False,
            "adjudication_visible": False,
        },
        "policy": labeling_policy(selection),
        "instructions": {
            "confirmation_required": True,
            "confirmation_must_follow_pivot": True,
            "confirmation_must_be_inside_window": True,
            "labels_must_alternate_direction": True,
            "allowed_direction_values": [
                "HIGH",
                "LOW",
            ],
            "allowed_tier_scope_pairs": [
                {
                    "tier": tier,
                    "scope": scope,
                }
                for tier, scope in sorted(
                    ALLOWED_TIER_SCOPE
                )
            ],
            "label_fields": [
                "label_id",
                "window_number",
                "pivot_index",
                "direction",
                "tier",
                "scope",
                "confirmed_at_index",
                "notes",
            ],
        },
        "windows": windows,
        "labels": [],
        "review_notes": "",
    }


def validate_label(
    label: Any,
    *,
    index: int,
    windows_by_number: dict[
        int,
        dict[str, Any],
    ],
) -> tuple[
    dict[str, Any] | None,
    list[str],
]:
    errors: list[str] = []
    prefix = f"label {index}"

    if not isinstance(label, dict):
        return None, [
            f"{prefix} must be an object"
        ]

    label_id = label.get("label_id")

    if (
        not isinstance(label_id, str)
        or not LABEL_ID_PATTERN.fullmatch(label_id)
    ):
        errors.append(
            f"{prefix}: invalid label_id"
        )

    try:
        window_number = int(
            label["window_number"]
        )
    except (KeyError, TypeError, ValueError):
        window_number = -1
        errors.append(
            f"{prefix}: invalid window_number"
        )

    window = windows_by_number.get(
        window_number
    )

    if window is None:
        errors.append(
            f"{prefix}: unknown window_number "
            f"{window_number}"
        )
        bars = 0
    else:
        bars = int(window["bars"])

    try:
        pivot_index = int(
            label["pivot_index"]
        )
    except (KeyError, TypeError, ValueError):
        pivot_index = -1
        errors.append(
            f"{prefix}: invalid pivot_index"
        )

    direction = label.get("direction")

    if direction not in ALLOWED_DIRECTIONS:
        errors.append(
            f"{prefix}: direction must be "
            "HIGH or LOW"
        )

    tier = label.get("tier")
    scope = label.get("scope")

    if (tier, scope) not in ALLOWED_TIER_SCOPE:
        errors.append(
            f"{prefix}: unsupported tier/scope "
            f"pair {tier!r}/{scope!r}"
        )

    try:
        confirmed_at_index = int(
            label["confirmed_at_index"]
        )
    except (KeyError, TypeError, ValueError):
        confirmed_at_index = -1
        errors.append(
            f"{prefix}: invalid confirmed_at_index"
        )

    notes = label.get("notes", "")

    if not isinstance(notes, str):
        errors.append(
            f"{prefix}: notes must be a string"
        )

    if bars:
        if not 0 <= pivot_index < bars:
            errors.append(
                f"{prefix}: pivot_index is outside "
                "the window"
            )

        if not 0 <= confirmed_at_index < bars:
            errors.append(
                f"{prefix}: confirmed_at_index is "
                "outside the window"
            )

    if confirmed_at_index <= pivot_index:
        errors.append(
            f"{prefix}: confirmation must occur "
            "after the pivot"
        )

    normalized = {
        "label_id": label_id,
        "window_number": window_number,
        "pivot_index": pivot_index,
        "direction": direction,
        "tier": tier,
        "scope": scope,
        "confirmed_at_index": (
            confirmed_at_index
        ),
        "notes": notes,
    }

    return normalized, errors


def validate_pass_document(
    document: dict[str, Any],
    *,
    selection_root: Path,
) -> dict[str, Any]:
    (
        selection,
        manifest_path,
        selection_windows,
    ) = load_selection(selection_root)

    errors: list[str] = []

    if document.get("schema_version") != (
        PASS_SCHEMA
    ):
        errors.append(
            "unsupported pass schema_version"
        )

    if document.get("protocol_id") != (
        selection["protocol_id"]
    ):
        errors.append(
            "pass protocol_id does not match "
            "selection manifest"
        )

    selection_block = document.get(
        "selection",
        {},
    )

    if selection_block.get(
        "manifest_sha256"
    ) != sha256(manifest_path):
        errors.append(
            "selection manifest SHA-256 mismatch"
        )

    try:
        pass_number = int(
            document["pass_number"]
        )
    except (KeyError, TypeError, ValueError):
        pass_number = -1
        errors.append("invalid pass_number")

    if pass_number not in (1, 2):
        errors.append(
            "pass_number must be 1 or 2"
        )

    annotator_id = document.get(
        "annotator_id"
    )

    if (
        not isinstance(annotator_id, str)
        or not annotator_id.strip()
    ):
        errors.append(
            "annotator_id must be non-empty"
        )

    status = document.get("status")

    if status not in {
        "DRAFT",
        "COMPLETE",
    }:
        errors.append(
            "status must be DRAFT or COMPLETE"
        )

    try:
        created_at = parse_utc(
            document.get("created_at_utc"),
            field="created_at_utc",
        )
    except ValueError as exc:
        created_at = datetime.min.replace(
            tzinfo=timezone.utc
        )
        errors.append(str(exc))

    completed_value = document.get(
        "completed_at_utc"
    )
    completed_at: datetime | None = None

    if status == "COMPLETE":
        try:
            completed_at = parse_utc(
                completed_value,
                field="completed_at_utc",
            )
        except ValueError as exc:
            errors.append(str(exc))

        if (
            completed_at is not None
            and completed_at < created_at
        ):
            errors.append(
                "completed_at_utc precedes "
                "created_at_utc"
            )
    elif completed_value is not None:
        errors.append(
            "DRAFT pass must have null "
            "completed_at_utc"
        )

    blindness = document.get(
        "blindness",
        {},
    )

    for key in (
        "predictions_visible",
        "engine_version_visible",
        "prior_pass_visible",
        "comparison_visible",
        "adjudication_visible",
    ):
        if blindness.get(key) is not False:
            errors.append(
                f"blindness control {key} "
                "must be false"
            )

    document_windows = document.get(
        "windows"
    )

    if document_windows != selection_windows:
        errors.append(
            "pass window inventory does not "
            "match selection manifest"
        )

    labels_value = document.get("labels")

    if not isinstance(labels_value, list):
        errors.append(
            "labels must be a list"
        )
        labels_value = []

    windows_by_number = {
        int(window["window_number"]): window
        for window in selection_windows
    }

    normalized_labels: list[
        dict[str, Any]
    ] = []

    for index, label in enumerate(
        labels_value,
        start=1,
    ):
        normalized, label_errors = (
            validate_label(
                label,
                index=index,
                windows_by_number=(
                    windows_by_number
                ),
            )
        )

        errors.extend(label_errors)

        if normalized is not None:
            normalized_labels.append(
                normalized
            )

    label_ids = [
        label["label_id"]
        for label in normalized_labels
    ]

    if len(label_ids) != len(set(label_ids)):
        errors.append(
            "label_id values must be unique"
        )

    identity_keys = [
        (
            label["window_number"],
            label["pivot_index"],
            label["direction"],
        )
        for label in normalized_labels
    ]

    if len(identity_keys) != len(
        set(identity_keys)
    ):
        errors.append(
            "duplicate window/pivot/direction labels"
        )

    by_window: dict[
        int,
        list[dict[str, Any]],
    ] = {}

    for label in normalized_labels:
        by_window.setdefault(
            label["window_number"],
            [],
        ).append(label)

    for window_number, window_labels in (
        sorted(by_window.items())
    ):
        ordered = sorted(
            window_labels,
            key=lambda value: (
                value["pivot_index"],
                value["confirmed_at_index"],
                value["direction"],
            ),
        )

        for left, right in zip(
            ordered,
            ordered[1:],
        ):
            if (
                left["direction"]
                == right["direction"]
            ):
                errors.append(
                    f"window {window_number}: "
                    "labels must alternate direction"
                )
                break

    fail(errors)

    return {
        "document": document,
        "pass_number": pass_number,
        "annotator_id": annotator_id,
        "status": status,
        "created_at": created_at,
        "completed_at": completed_at,
        "labels": normalized_labels,
        "selection_manifest_sha256": sha256(
            manifest_path
        ),
        "protocol_id": selection[
            "protocol_id"
        ],
        "policy": document.get(
            "policy",
            {},
        ),
    }


def load_and_validate_pass(
    path: Path,
    *,
    selection_root: Path,
) -> dict[str, Any]:
    document = load_json(path)

    validated = validate_pass_document(
        document,
        selection_root=selection_root,
    )

    validated["path"] = path.resolve()
    validated["sha256"] = sha256(path)

    return validated


def ensure_second_pass_delay(
    *,
    prior: dict[str, Any],
    created_at: datetime,
    minimum_days: int,
) -> None:
    if prior["pass_number"] != 1:
        raise SystemExit(
            "REFUSED: prior pass must be pass 1"
        )

    if prior["status"] != "COMPLETE":
        raise SystemExit(
            "REFUSED: pass 1 must be COMPLETE "
            "before pass 2 is prepared"
        )

    completed_at = prior["completed_at"]

    if completed_at is None:
        raise SystemExit(
            "REFUSED: pass 1 has no completion time"
        )

    earliest = (
        completed_at
        + timedelta(days=minimum_days)
    )

    if created_at < earliest:
        raise SystemExit(
            "REFUSED: pass 2 cannot begin before "
            f"{utc_text(earliest)}"
        )


def compare_passes(
    first: dict[str, Any],
    second: dict[str, Any],
    *,
    minimum_days: int,
) -> dict[str, Any]:
    errors: list[str] = []

    if first["pass_number"] != 1:
        errors.append(
            "first document is not pass 1"
        )

    if second["pass_number"] != 2:
        errors.append(
            "second document is not pass 2"
        )

    if first["status"] != "COMPLETE":
        errors.append(
            "pass 1 is not COMPLETE"
        )

    if second["status"] != "COMPLETE":
        errors.append(
            "pass 2 is not COMPLETE"
        )

    if first["protocol_id"] != second[
        "protocol_id"
    ]:
        errors.append(
            "pass protocol IDs differ"
        )

    if first[
        "selection_manifest_sha256"
    ] != second[
        "selection_manifest_sha256"
    ]:
        errors.append(
            "pass selection manifest hashes differ"
        )

    first_completed = first["completed_at"]
    second_created = second["created_at"]

    if first_completed is None:
        errors.append(
            "pass 1 completion time is missing"
        )
        separation_hours = None
    else:
        separation = (
            second_created - first_completed
        )
        separation_hours = (
            separation.total_seconds() / 3600
        )

        if separation < timedelta(
            days=minimum_days
        ):
            errors.append(
                "minimum delay between passes "
                "was not satisfied"
            )

    fail(errors)

    first_by_key = {
        (
            label["window_number"],
            label["pivot_index"],
            label["direction"],
        ): label
        for label in first["labels"]
    }

    second_by_key = {
        (
            label["window_number"],
            label["pivot_index"],
            label["direction"],
        ): label
        for label in second["labels"]
    }

    keys = sorted(
        set(first_by_key) | set(second_by_key),
        key=lambda value: (
            value[0],
            value[1],
            value[2],
        ),
    )

    agreements: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []

    semantic_fields = (
        "tier",
        "scope",
        "confirmed_at_index",
    )

    for key in keys:
        first_label = first_by_key.get(key)
        second_label = second_by_key.get(key)

        identity = {
            "window_number": key[0],
            "pivot_index": key[1],
            "direction": key[2],
        }

        if first_label is None:
            conflicts.append(
                {
                    "conflict_type":
                        "PASS_2_ONLY",
                    "identity": identity,
                    "pass_1": None,
                    "pass_2": second_label,
                    "resolution": None,
                }
            )
            continue

        if second_label is None:
            conflicts.append(
                {
                    "conflict_type":
                        "PASS_1_ONLY",
                    "identity": identity,
                    "pass_1": first_label,
                    "pass_2": None,
                    "resolution": None,
                }
            )
            continue

        differences = {
            field: {
                "pass_1": first_label[field],
                "pass_2": second_label[field],
            }
            for field in semantic_fields
            if first_label[field] != (
                second_label[field]
            )
        }

        if differences:
            conflicts.append(
                {
                    "conflict_type":
                        "ATTRIBUTE_CONFLICT",
                    "identity": identity,
                    "differences": differences,
                    "pass_1": first_label,
                    "pass_2": second_label,
                    "resolution": None,
                }
            )
        else:
            agreements.append(
                {
                    "identity": identity,
                    "label": first_label,
                }
            )

    return {
        "agreements": agreements,
        "conflicts": conflicts,
        "separation_hours": separation_hours,
    }


def command_prepare(
    args: argparse.Namespace,
) -> int:
    selection_root = args.selection_root.resolve()
    output = args.output.resolve()

    if output.exists():
        raise SystemExit(
            f"REFUSED: output already exists: {output}"
        )

    if args.pass_number not in (1, 2):
        raise SystemExit(
            "REFUSED: pass number must be 1 or 2"
        )

    annotator_id = args.annotator_id.strip()

    if not annotator_id:
        raise SystemExit(
            "REFUSED: annotator ID must be non-empty"
        )

    created_at = (
        parse_utc(
            args.created_at,
            field="--created-at",
        )
        if args.created_at
        else utc_now()
    )

    document = build_pass_document(
        selection_root=selection_root,
        pass_number=args.pass_number,
        annotator_id=annotator_id,
        created_at=created_at,
    )

    if args.pass_number == 1:
        if args.prior_pass is not None:
            raise SystemExit(
                "REFUSED: pass 1 cannot have "
                "a prior pass"
            )
    else:
        if args.prior_pass is None:
            raise SystemExit(
                "REFUSED: pass 2 requires "
                "--prior-pass"
            )

        prior = load_and_validate_pass(
            args.prior_pass.resolve(),
            selection_root=selection_root,
        )

        minimum_days = int(
            document["policy"][
                "minimum_days_between_passes"
            ]
        )

        ensure_second_pass_delay(
            prior=prior,
            created_at=created_at,
            minimum_days=minimum_days,
        )

    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output.write_text(
        json.dumps(document, indent=2) + "\n",
        encoding="utf-8",
    )

    print()
    print("BLIND LABEL PASS PREPARED")
    print("=" * 76)
    print("Pass:", args.pass_number)
    print("Annotator:", annotator_id)
    print("Created:", utc_text(created_at))
    print("Windows:", len(document["windows"]))
    print("Predictions visible: False")
    print("Engine version visible: False")
    print("Output:", output)
    return 0


def command_validate(
    args: argparse.Namespace,
) -> int:
    validated = load_and_validate_pass(
        args.pass_file.resolve(),
        selection_root=(
            args.selection_root.resolve()
        ),
    )

    print()
    print("BLIND LABEL PASS VALID")
    print("=" * 76)
    print("Pass:", validated["pass_number"])
    print("Status:", validated["status"])
    print(
        "Annotator:",
        validated["annotator_id"],
    )
    print("Labels:", len(validated["labels"]))
    print("SHA-256:", validated["sha256"])
    return 0


def command_compare(
    args: argparse.Namespace,
) -> int:
    selection_root = (
        args.selection_root.resolve()
    )
    output = args.output.resolve()

    if output.exists():
        raise SystemExit(
            f"REFUSED: output already exists: {output}"
        )

    first = load_and_validate_pass(
        args.pass_one.resolve(),
        selection_root=selection_root,
    )

    second = load_and_validate_pass(
        args.pass_two.resolve(),
        selection_root=selection_root,
    )

    minimum_days = int(
        first["policy"].get(
            "minimum_days_between_passes",
            3,
        )
    )

    result = compare_passes(
        first,
        second,
        minimum_days=minimum_days,
    )

    conflicts = result["conflicts"]

    document = {
        "schema_version": COMPARISON_SCHEMA,
        "protocol_id": first["protocol_id"],
        "selection_manifest_sha256": first[
            "selection_manifest_sha256"
        ],
        "status": (
            "ADJUDICATION_REQUIRED"
            if conflicts
            else "NO_CONFLICTS"
        ),
        "generated_at_utc": utc_text(
            utc_now()
        ),
        "policy": {
            "predictions_visible": False,
            "engine_version_visible": False,
            "auto_resolution_performed": False,
            "minimum_days_between_passes": (
                minimum_days
            ),
            "conflicts_require_explicit_adjudication": (
                True
            ),
        },
        "passes": {
            "pass_1": {
                "path": display_path(
                    first["path"]
                ),
                "sha256": first["sha256"],
                "annotator_id": first[
                    "annotator_id"
                ],
                "created_at_utc": utc_text(
                    first["created_at"]
                ),
                "completed_at_utc": utc_text(
                    first["completed_at"]
                ),
                "labels": len(
                    first["labels"]
                ),
            },
            "pass_2": {
                "path": display_path(
                    second["path"]
                ),
                "sha256": second["sha256"],
                "annotator_id": second[
                    "annotator_id"
                ],
                "created_at_utc": utc_text(
                    second["created_at"]
                ),
                "completed_at_utc": utc_text(
                    second["completed_at"]
                ),
                "labels": len(
                    second["labels"]
                ),
            },
            "separation_hours": result[
                "separation_hours"
            ],
        },
        "summary": {
            "agreements": len(
                result["agreements"]
            ),
            "conflicts": len(conflicts),
            "pass_1_only": sum(
                item["conflict_type"]
                == "PASS_1_ONLY"
                for item in conflicts
            ),
            "pass_2_only": sum(
                item["conflict_type"]
                == "PASS_2_ONLY"
                for item in conflicts
            ),
            "attribute_conflicts": sum(
                item["conflict_type"]
                == "ATTRIBUTE_CONFLICT"
                for item in conflicts
            ),
        },
        "agreements": result["agreements"],
        "conflicts": conflicts,
    }

    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output.write_text(
        json.dumps(document, indent=2) + "\n",
        encoding="utf-8",
    )

    print()
    print("BLIND LABEL PASSES COMPARED")
    print("=" * 76)
    print("Status:", document["status"])
    print(
        "Agreements:",
        document["summary"]["agreements"],
    )
    print(
        "Conflicts:",
        document["summary"]["conflicts"],
    )
    print(
        "Separation hours:",
        result["separation_hours"],
    )
    print("Output:", output)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    prepare = subparsers.add_parser(
        "prepare",
        help="Create an empty blind labeling-pass template.",
    )
    prepare.add_argument(
        "--selection-root",
        type=Path,
        required=True,
    )
    prepare.add_argument(
        "--output",
        type=Path,
        required=True,
    )
    prepare.add_argument(
        "--pass-number",
        type=int,
        required=True,
    )
    prepare.add_argument(
        "--annotator-id",
        required=True,
    )
    prepare.add_argument(
        "--prior-pass",
        type=Path,
    )
    prepare.add_argument(
        "--created-at",
        help=(
            "Optional explicit ISO-8601 UTC time; "
            "default is current UTC."
        ),
    )
    prepare.set_defaults(
        handler=command_prepare
    )

    validate = subparsers.add_parser(
        "validate",
        help="Validate one blind labeling-pass document.",
    )
    validate.add_argument(
        "--selection-root",
        type=Path,
        required=True,
    )
    validate.add_argument(
        "--pass-file",
        type=Path,
        required=True,
    )
    validate.set_defaults(
        handler=command_validate
    )

    compare = subparsers.add_parser(
        "compare",
        help=(
            "Compare two completed blind passes "
            "without auto-resolving conflicts."
        ),
    )
    compare.add_argument(
        "--selection-root",
        type=Path,
        required=True,
    )
    compare.add_argument(
        "--pass-one",
        type=Path,
        required=True,
    )
    compare.add_argument(
        "--pass-two",
        type=Path,
        required=True,
    )
    compare.add_argument(
        "--output",
        type=Path,
        required=True,
    )
    compare.set_defaults(
        handler=command_compare
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())

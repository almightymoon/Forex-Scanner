#!/usr/bin/env python3
"""Manage explicit adjudication of two blind labeling passes.

This tool:

- loads only selected windows and completed blind passes;
- never imports or executes the swing detector;
- never loads predictions;
- recomputes pass agreements/conflicts independently;
- creates one explicit resolution slot per conflict;
- permits PASS_1, PASS_2, CUSTOM, or EXCLUDE decisions;
- performs no automatic conflict resolution;
- validates the resolved label sequence before final freezing.

Final benchmark freezing is a separate operation.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

SCHEMA_VERSION = (
    "XAUUSD_H1_BLIND_ADJUDICATION_V1"
)

ALLOWED_DECISIONS = {
    "PASS_1",
    "PASS_2",
    "CUSTOM",
    "EXCLUDE",
}


def load_pass_manager():
    path = (
        ROOT
        / "scripts"
        / "manage_xauusd_h1_post_2026h1_label_passes.py"
    )

    spec = importlib.util.spec_from_file_location(
        "fxn_post_2026h1_pass_manager",
        path,
    )

    if spec is None or spec.loader is None:
        raise RuntimeError(
            f"Unable to load {path}"
        )

    module = importlib.util.module_from_spec(
        spec
    )
    spec.loader.exec_module(module)
    return module


PASSES = load_pass_manager()


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
            f"REFUSED: invalid JSON in "
            f"{path}: {exc}"
        ) from exc

    if not isinstance(value, dict):
        raise SystemExit(
            f"REFUSED: JSON root must be "
            f"an object: {path}"
        )

    return value


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def fail(errors: list[str]) -> None:
    if errors:
        raise SystemExit(
            "REFUSED:\n- "
            + "\n- ".join(errors)
        )


def source_summary(
    validated: dict[str, Any],
) -> dict[str, Any]:
    return {
        "path": PASSES.display_path(
            validated["path"]
        ),
        "sha256": validated["sha256"],
        "pass_number": validated[
            "pass_number"
        ],
        "annotator_id": validated[
            "annotator_id"
        ],
        "created_at_utc": PASSES.utc_text(
            validated["created_at"]
        ),
        "completed_at_utc": PASSES.utc_text(
            validated["completed_at"]
        ),
        "labels": len(
            validated["labels"]
        ),
    }


def validate_comparison(
    comparison_path: Path,
    *,
    first: dict[str, Any],
    second: dict[str, Any],
    minimum_days: int,
) -> tuple[
    dict[str, Any],
    dict[str, Any],
]:
    document = load_json(comparison_path)
    errors: list[str] = []

    if document.get(
        "schema_version"
    ) != PASSES.COMPARISON_SCHEMA:
        errors.append(
            "unsupported comparison schema"
        )

    if document.get(
        "protocol_id"
    ) != first["protocol_id"]:
        errors.append(
            "comparison protocol_id mismatch"
        )

    if document.get(
        "selection_manifest_sha256"
    ) != first[
        "selection_manifest_sha256"
    ]:
        errors.append(
            "comparison selection hash mismatch"
        )

    policy = document.get("policy", {})

    if policy.get(
        "predictions_visible"
    ) is not False:
        errors.append(
            "comparison predictions_visible "
            "must be false"
        )

    if policy.get(
        "engine_version_visible"
    ) is not False:
        errors.append(
            "comparison engine_version_visible "
            "must be false"
        )

    if policy.get(
        "auto_resolution_performed"
    ) is not False:
        errors.append(
            "comparison must not perform "
            "automatic resolution"
        )

    passes = document.get(
        "passes",
        {},
    )

    if passes.get(
        "pass_1",
        {},
    ).get("sha256") != first["sha256"]:
        errors.append(
            "comparison pass 1 hash mismatch"
        )

    if passes.get(
        "pass_2",
        {},
    ).get("sha256") != second["sha256"]:
        errors.append(
            "comparison pass 2 hash mismatch"
        )

    expected = PASSES.compare_passes(
        first,
        second,
        minimum_days=minimum_days,
    )

    if document.get(
        "agreements"
    ) != expected["agreements"]:
        errors.append(
            "comparison agreements do not "
            "match recomputed agreements"
        )

    if document.get(
        "conflicts"
    ) != expected["conflicts"]:
        errors.append(
            "comparison conflicts do not "
            "match recomputed conflicts"
        )

    expected_status = (
        "ADJUDICATION_REQUIRED"
        if expected["conflicts"]
        else "NO_CONFLICTS"
    )

    if document.get(
        "status"
    ) != expected_status:
        errors.append(
            "comparison status mismatch"
        )

    fail(errors)

    return document, expected


def conflict_record(
    number: int,
    conflict: dict[str, Any],
) -> dict[str, Any]:
    return {
        "conflict_id": f"CONFLICT_{number:03d}",
        "conflict_type": conflict[
            "conflict_type"
        ],
        "identity": conflict["identity"],
        "differences": conflict.get(
            "differences"
        ),
        "pass_1": conflict.get("pass_1"),
        "pass_2": conflict.get("pass_2"),
        "decision": None,
        "custom_label": None,
        "notes": "",
    }


def build_document(
    *,
    selection_root: Path,
    pass_one_path: Path,
    pass_two_path: Path,
    comparison_path: Path,
    adjudicator_id: str,
    created_at: datetime,
) -> dict[str, Any]:
    first = PASSES.load_and_validate_pass(
        pass_one_path.resolve(),
        selection_root=selection_root,
    )

    second = PASSES.load_and_validate_pass(
        pass_two_path.resolve(),
        selection_root=selection_root,
    )

    minimum_days = int(
        first["policy"].get(
            "minimum_days_between_passes",
            3,
        )
    )

    comparison, recomputed = (
        validate_comparison(
            comparison_path.resolve(),
            first=first,
            second=second,
            minimum_days=minimum_days,
        )
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "protocol_id": first[
            "protocol_id"
        ],
        "selection_manifest_sha256": first[
            "selection_manifest_sha256"
        ],
        "status": "DRAFT",
        "adjudicator_id": adjudicator_id,
        "created_at_utc": PASSES.utc_text(
            created_at
        ),
        "completed_at_utc": None,
        "blindness": {
            "predictions_visible": False,
            "engine_version_visible": False,
        },
        "policy": {
            "auto_resolution_performed": False,
            "every_conflict_requires_decision": (
                True
            ),
            "decision_values": sorted(
                ALLOWED_DECISIONS
            ),
            "custom_identity_must_match_conflict": (
                True
            ),
            "final_structure_validation_required": (
                True
            ),
        },
        "sources": {
            "pass_1": source_summary(first),
            "pass_2": source_summary(second),
            "comparison": {
                "path": PASSES.display_path(
                    comparison_path.resolve()
                ),
                "sha256": PASSES.sha256(
                    comparison_path.resolve()
                ),
                "status": comparison["status"],
                "agreements": len(
                    recomputed["agreements"]
                ),
                "conflicts": len(
                    recomputed["conflicts"]
                ),
            },
        },
        "agreements": recomputed[
            "agreements"
        ],
        "conflicts": [
            conflict_record(
                number,
                conflict,
            )
            for number, conflict in enumerate(
                recomputed["conflicts"],
                start=1,
            )
        ],
        "review_notes": "",
    }


def allowed_for_conflict(
    conflict: dict[str, Any],
) -> set[str]:
    allowed = {
        "CUSTOM",
        "EXCLUDE",
    }

    if conflict.get("pass_1") is not None:
        allowed.add("PASS_1")

    if conflict.get("pass_2") is not None:
        allowed.add("PASS_2")

    return allowed


def identity_tuple(
    value: dict[str, Any],
) -> tuple[int, int, str]:
    return (
        int(value["window_number"]),
        int(value["pivot_index"]),
        str(value["direction"]),
    )


def chosen_label(
    conflict: dict[str, Any],
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
    decision = conflict.get("decision")
    prefix = (
        str(conflict.get("conflict_id"))
        or f"conflict {index}"
    )

    allowed = allowed_for_conflict(
        conflict
    )

    if decision not in allowed:
        return None, [
            f"{prefix}: decision must be one of "
            f"{sorted(allowed)}"
        ]

    notes = conflict.get("notes", "")

    if not isinstance(notes, str) or not (
        notes.strip()
    ):
        errors.append(
            f"{prefix}: adjudication notes "
            "must be non-empty"
        )

    if decision == "EXCLUDE":
        return None, errors

    if decision == "PASS_1":
        label = conflict.get("pass_1")
    elif decision == "PASS_2":
        label = conflict.get("pass_2")
    else:
        label = conflict.get(
            "custom_label"
        )

    normalized, label_errors = (
        PASSES.validate_label(
            label,
            index=index,
            windows_by_number=(
                windows_by_number
            ),
        )
    )

    errors.extend(
        f"{prefix}: {error}"
        for error in label_errors
    )

    if normalized is not None:
        expected_identity = identity_tuple(
            conflict["identity"]
        )

        actual_identity = identity_tuple(
            normalized
        )

        if actual_identity != expected_identity:
            errors.append(
                f"{prefix}: resolved label identity "
                "does not match conflict identity"
            )

    return normalized, errors


def validate_document(
    document: dict[str, Any],
    *,
    selection_root: Path,
    pass_one_path: Path,
    pass_two_path: Path,
    comparison_path: Path,
) -> dict[str, Any]:
    first = PASSES.load_and_validate_pass(
        pass_one_path.resolve(),
        selection_root=selection_root,
    )

    second = PASSES.load_and_validate_pass(
        pass_two_path.resolve(),
        selection_root=selection_root,
    )

    minimum_days = int(
        first["policy"].get(
            "minimum_days_between_passes",
            3,
        )
    )

    comparison, recomputed = (
        validate_comparison(
            comparison_path.resolve(),
            first=first,
            second=second,
            minimum_days=minimum_days,
        )
    )

    errors: list[str] = []

    if document.get(
        "schema_version"
    ) != SCHEMA_VERSION:
        errors.append(
            "unsupported adjudication schema"
        )

    if document.get(
        "protocol_id"
    ) != first["protocol_id"]:
        errors.append(
            "adjudication protocol_id mismatch"
        )

    if document.get(
        "selection_manifest_sha256"
    ) != first[
        "selection_manifest_sha256"
    ]:
        errors.append(
            "adjudication selection hash mismatch"
        )

    adjudicator_id = document.get(
        "adjudicator_id"
    )

    if (
        not isinstance(adjudicator_id, str)
        or not adjudicator_id.strip()
    ):
        errors.append(
            "adjudicator_id must be non-empty"
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
        created_at = PASSES.parse_utc(
            document.get("created_at_utc"),
            field="created_at_utc",
        )
    except ValueError as exc:
        errors.append(str(exc))
        created_at = datetime.min.replace(
            tzinfo=timezone.utc
        )

    completed_value = document.get(
        "completed_at_utc"
    )
    completed_at: datetime | None = None

    if status == "COMPLETE":
        try:
            completed_at = PASSES.parse_utc(
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
            "DRAFT adjudication must have null "
            "completed_at_utc"
        )

    blindness = document.get(
        "blindness",
        {},
    )

    if blindness.get(
        "predictions_visible"
    ) is not False:
        errors.append(
            "predictions_visible must be false"
        )

    if blindness.get(
        "engine_version_visible"
    ) is not False:
        errors.append(
            "engine_version_visible must be false"
        )

    policy = document.get("policy", {})

    if policy.get(
        "auto_resolution_performed"
    ) is not False:
        errors.append(
            "auto_resolution_performed "
            "must be false"
        )

    sources = document.get("sources", {})

    if sources.get(
        "pass_1",
        {},
    ).get("sha256") != first["sha256"]:
        errors.append(
            "adjudication pass 1 hash mismatch"
        )

    if sources.get(
        "pass_2",
        {},
    ).get("sha256") != second["sha256"]:
        errors.append(
            "adjudication pass 2 hash mismatch"
        )

    if sources.get(
        "comparison",
        {},
    ).get("sha256") != PASSES.sha256(
        comparison_path.resolve()
    ):
        errors.append(
            "adjudication comparison hash mismatch"
        )

    expected_conflicts = [
        conflict_record(
            number,
            conflict,
        )
        for number, conflict in enumerate(
            recomputed["conflicts"],
            start=1,
        )
    ]

    conflicts = document.get(
        "conflicts"
    )

    if not isinstance(conflicts, list):
        errors.append(
            "conflicts must be a list"
        )
        conflicts = []

    if len(conflicts) != len(
        expected_conflicts
    ):
        errors.append(
            "adjudication conflict count mismatch"
        )

    for index, (
        actual,
        expected,
    ) in enumerate(
        zip(
            conflicts,
            expected_conflicts,
        ),
        start=1,
    ):
        for key in (
            "conflict_id",
            "conflict_type",
            "identity",
            "differences",
            "pass_1",
            "pass_2",
        ):
            if actual.get(key) != expected.get(
                key
            ):
                errors.append(
                    f"conflict {index}: immutable "
                    f"field {key} was changed"
                )

    if document.get(
        "agreements"
    ) != recomputed["agreements"]:
        errors.append(
            "adjudication agreements mismatch"
        )

    (
        _,
        _,
        windows,
    ) = PASSES.load_selection(
        selection_root
    )

    windows_by_number = {
        int(window["window_number"]): window
        for window in windows
    }

    resolved_labels = [
        agreement["label"]
        for agreement in recomputed[
            "agreements"
        ]
    ]

    resolution_errors: list[str] = []

    for index, conflict in enumerate(
        conflicts,
        start=1,
    ):
        decision = conflict.get(
            "decision"
        )

        if status == "DRAFT" and (
            decision is None
        ):
            continue

        resolved, item_errors = (
            chosen_label(
                conflict,
                index=index,
                windows_by_number=(
                    windows_by_number
                ),
            )
        )

        resolution_errors.extend(
            item_errors
        )

        if resolved is not None:
            resolved_labels.append(
                resolved
            )

    errors.extend(resolution_errors)

    if status == "COMPLETE":
        unresolved = [
            conflict.get("conflict_id")
            for conflict in conflicts
            if conflict.get("decision")
            is None
        ]

        if unresolved:
            errors.append(
                "complete adjudication contains "
                f"unresolved conflicts: {unresolved}"
            )

        if not errors:
            normalized_final = []

            for number, label in enumerate(
                sorted(
                    resolved_labels,
                    key=lambda value: (
                        value["window_number"],
                        value["pivot_index"],
                        value["direction"],
                    ),
                ),
                start=1,
            ):
                normalized_final.append(
                    {
                        **label,
                        "label_id": (
                            f"ADJUDICATED_{number:04d}"
                        ),
                    }
                )

            synthetic = (
                PASSES.build_pass_document(
                    selection_root=(
                        selection_root
                    ),
                    pass_number=2,
                    annotator_id=(
                        adjudicator_id
                    ),
                    created_at=created_at,
                )
            )

            synthetic["status"] = "COMPLETE"
            synthetic[
                "completed_at_utc"
            ] = PASSES.utc_text(
                completed_at
            )
            synthetic["labels"] = (
                normalized_final
            )

            try:
                PASSES.validate_pass_document(
                    synthetic,
                    selection_root=(
                        selection_root
                    ),
                )
            except SystemExit as exc:
                errors.append(
                    "resolved final label structure "
                    f"is invalid: {exc}"
                )

    fail(errors)

    return {
        "status": status,
        "adjudicator_id": adjudicator_id,
        "created_at": created_at,
        "completed_at": completed_at,
        "agreements": recomputed[
            "agreements"
        ],
        "conflicts": conflicts,
        "resolved_labels": (
            sorted(
                resolved_labels,
                key=lambda value: (
                    value["window_number"],
                    value["pivot_index"],
                    value["direction"],
                ),
            )
            if status == "COMPLETE"
            else []
        ),
        "protocol_id": first[
            "protocol_id"
        ],
        "selection_manifest_sha256": (
            first[
                "selection_manifest_sha256"
            ]
        ),
        "pass_1": first,
        "pass_2": second,
        "comparison": comparison,
    }


def command_prepare(
    args: argparse.Namespace,
) -> int:
    output = args.output.resolve()

    if output.exists():
        raise SystemExit(
            f"REFUSED: output already exists: "
            f"{output}"
        )

    adjudicator_id = (
        args.adjudicator_id.strip()
    )

    if not adjudicator_id:
        raise SystemExit(
            "REFUSED: adjudicator ID must "
            "be non-empty"
        )

    created_at = (
        PASSES.parse_utc(
            args.created_at,
            field="--created-at",
        )
        if args.created_at
        else utc_now()
    )

    document = build_document(
        selection_root=(
            args.selection_root.resolve()
        ),
        pass_one_path=(
            args.pass_one.resolve()
        ),
        pass_two_path=(
            args.pass_two.resolve()
        ),
        comparison_path=(
            args.comparison.resolve()
        ),
        adjudicator_id=adjudicator_id,
        created_at=created_at,
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
    print("ADJUDICATION TEMPLATE PREPARED")
    print("=" * 76)
    print("Status: DRAFT")
    print(
        "Adjudicator:",
        adjudicator_id,
    )
    print(
        "Agreements:",
        len(document["agreements"]),
    )
    print(
        "Conflicts:",
        len(document["conflicts"]),
    )
    print("Automatic resolutions: 0")
    print("Predictions visible: False")
    print("Engine version visible: False")
    print("Output:", output)
    return 0


def command_validate(
    args: argparse.Namespace,
) -> int:
    path = args.adjudication.resolve()
    document = load_json(path)

    result = validate_document(
        document,
        selection_root=(
            args.selection_root.resolve()
        ),
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

    print()
    print("ADJUDICATION DOCUMENT VALID")
    print("=" * 76)
    print("Status:", result["status"])
    print(
        "Adjudicator:",
        result["adjudicator_id"],
    )
    print(
        "Agreements:",
        len(result["agreements"]),
    )
    print(
        "Conflicts:",
        len(result["conflicts"]),
    )
    print(
        "Resolved final labels:",
        len(result["resolved_labels"]),
    )
    print(
        "SHA-256:",
        PASSES.sha256(path),
    )
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
        help=(
            "Create an explicit adjudication "
            "template from two completed passes."
        ),
    )

    validate = subparsers.add_parser(
        "validate",
        help=(
            "Validate an adjudication document "
            "and its resolved final structure."
        ),
    )

    for command in (
        prepare,
        validate,
    ):
        command.add_argument(
            "--selection-root",
            type=Path,
            required=True,
        )
        command.add_argument(
            "--pass-one",
            type=Path,
            required=True,
        )
        command.add_argument(
            "--pass-two",
            type=Path,
            required=True,
        )
        command.add_argument(
            "--comparison",
            type=Path,
            required=True,
        )

    prepare.add_argument(
        "--output",
        type=Path,
        required=True,
    )
    prepare.add_argument(
        "--adjudicator-id",
        required=True,
    )
    prepare.add_argument(
        "--created-at",
        help=(
            "Optional explicit ISO-8601 UTC "
            "timestamp."
        ),
    )
    prepare.set_defaults(
        handler=command_prepare
    )

    validate.add_argument(
        "--adjudication",
        type=Path,
        required=True,
    )
    validate.set_defaults(
        handler=command_validate
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())

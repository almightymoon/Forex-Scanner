#!/usr/bin/env python3
"""Validate a human swing benchmark against its frozen candle checksum."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from swing_engine.annotations import validate_annotation_document


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate human swing annotations")
    parser.add_argument(
        "labels",
        nargs="?",
        type=Path,
        default=Path("benchmarks/labels/XAUUSD_H1.human.json"),
    )
    parser.add_argument("--json", dest="json_output", type=Path)
    args = parser.parse_args()

    issues = validate_annotation_document(args.labels)
    errors = [issue for issue in issues if issue.severity == "ERROR"]
    warnings = [issue for issue in issues if issue.severity == "WARNING"]

    print(f"{args.labels}: {len(errors)} error(s), {len(warnings)} warning(s)")
    for issue in issues:
        location = "/".join(value for value in (issue.sample_id, issue.label_id) if value)
        suffix = f" [{location}]" if location else ""
        print(f"{issue.severity:7} {issue.code}: {issue.message}{suffix}")

    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(
            json.dumps({"issues": [issue.to_dict() for issue in issues]}, indent=2),
            encoding="utf-8",
        )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())

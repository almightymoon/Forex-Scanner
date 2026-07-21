#!/usr/bin/env python3
"""Blind labeling-pass manager for the 2022–2024 retrospective holdout.

Thin wrapper around the post-2026H1 pass manager. All validation, pass
separation, and conflict comparison logic is reused unchanged. This wrapper
only documents retrospective defaults and refuses prospective-protocol misuse.

Does not generate labels, predictions, or engine output.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

DEFAULT_SELECTION_ROOT = (
    ROOT
    / "benchmarks"
    / "data"
    / "locked"
    / "XAUUSD"
    / "H1"
    / "retrospective_2022_2024"
    / "windows_v1"
)

DEFAULT_LABEL_ROOT = (
    ROOT
    / "benchmarks"
    / "data"
    / "locked"
    / "XAUUSD"
    / "H1"
    / "retrospective_2022_2024"
    / "labels"
)


def load_pass_manager():
    path = (
        ROOT
        / "scripts"
        / "manage_xauusd_h1_post_2026h1_label_passes.py"
    )
    spec = importlib.util.spec_from_file_location(
        "fxn_retrospective_pass_manager_impl",
        path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    print(
        "RETROSPECTIVE_HOLDOUT labeling support\n"
        f"Default selection root: {DEFAULT_SELECTION_ROOT}\n"
        f"Default label root:     {DEFAULT_LABEL_ROOT}\n"
        "This wrapper never auto-fills human labels.\n"
        "Begin pass 1 with an empty template only.\n",
        file=sys.stderr,
    )
    module = load_pass_manager()
    return int(module.main())


if __name__ == "__main__":
    raise SystemExit(main())

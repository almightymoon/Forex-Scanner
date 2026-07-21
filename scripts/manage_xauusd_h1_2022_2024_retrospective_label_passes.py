#!/usr/bin/env python3
"""Blind labeling-pass manager for the 2022–2024 retrospective holdout.

Thin wrapper around the post-2026H1 pass manager. A retrospective selection
adapter validates the native RETROSPECTIVE_HOLDOUT selection schema and exposes
an in-memory compatibility view to the shared helper. The committed
selection_manifest.json bytes remain the only hashed evidence path.

Does not generate labels, predictions, or engine output.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.xauusd_h1_retrospective_selection_adapter import (  # noqa: E402
    install_on_pass_module,
)


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
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    install_on_pass_module(module)
    return module


def main() -> int:
    print(
        "RETROSPECTIVE_HOLDOUT labeling support\n"
        f"Default selection root: {DEFAULT_SELECTION_ROOT}\n"
        f"Default label root:     {DEFAULT_LABEL_ROOT}\n"
        "Native retrospective selection schema is adapted in-memory only.\n"
        "This wrapper never auto-fills human labels.\n"
        "Begin pass 1 with an empty template only.\n",
        file=sys.stderr,
    )
    module = load_pass_manager()
    return int(module.main())


if __name__ == "__main__":
    raise SystemExit(main())

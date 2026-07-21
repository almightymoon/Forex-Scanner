#!/usr/bin/env python3
"""Explicit adjudication for the 2022–2024 retrospective holdout.

Thin wrapper around the post-2026H1 adjudication manager. Installs the
retrospective selection adapter onto the shared pass helper so native
RETROSPECTIVE_HOLDOUT manifests are accepted without rewriting committed files.

Decisions must be one of PASS_1, PASS_2, CUSTOM, or EXCLUDE, with nonempty
notes. No automatic conflict resolution. Never runs detection or evaluation.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.xauusd_h1_retrospective_selection_adapter import (  # noqa: E402
    install_on_module_with_passes,
)


def load_adjudication():
    path = (
        ROOT
        / "scripts"
        / "manage_xauusd_h1_post_2026h1_adjudication.py"
    )
    spec = importlib.util.spec_from_file_location(
        "fxn_retrospective_adjudication_impl",
        path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    install_on_module_with_passes(module)
    return module


def main() -> int:
    print(
        "RETROSPECTIVE_HOLDOUT adjudication support\n"
        "Allowed decisions: PASS_1 | PASS_2 | CUSTOM | EXCLUDE\n"
        "Nonempty notes are required for every decision.\n",
        file=sys.stderr,
    )
    module = load_adjudication()
    return int(module.main())


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Explicit adjudication for the 2022–2024 retrospective holdout.

Thin wrapper around the post-2026H1 adjudication manager. Decisions must be
one of PASS_1, PASS_2, CUSTOM, or EXCLUDE, with nonempty notes. No automatic
conflict resolution. Never runs detection or evaluation.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


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
    spec.loader.exec_module(module)
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

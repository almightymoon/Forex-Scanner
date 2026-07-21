#!/usr/bin/env python3
"""Freeze adjudicated labels for the 2022–2024 retrospective holdout.

Thin wrapper around the post-2026H1 label freezer with retrospective package
naming. Never runs candidate/baseline detection or evaluation.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_freezer():
    path = (
        ROOT
        / "scripts"
        / "freeze_xauusd_h1_post_2026h1_labels.py"
    )
    spec = importlib.util.spec_from_file_location(
        "fxn_retrospective_freezer_impl",
        path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    print(
        "RETROSPECTIVE_HOLDOUT label freeze support\n"
        "Freeze only after explicit human adjudication.\n"
        "Passing later retrospective evaluation cannot emit "
        "PROMOTE_V2_3_0_FINAL.\n",
        file=sys.stderr,
    )
    module = load_freezer()
    module.DATA_FILENAME = (
        "XAUUSD_H1_2022_2024_retrospective_locked.real.csv.gz"
    )
    module.LABELS_FILENAME = (
        "XAUUSD_H1_2022_2024_retrospective_locked.human.json"
    )
    module.MANIFEST_FILENAME = (
        "XAUUSD_H1_2022_2024_retrospective_locked."
        "human.manifest.json"
    )
    return int(module.main())


if __name__ == "__main__":
    raise SystemExit(main())

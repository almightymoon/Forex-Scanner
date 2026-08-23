"""Cold-import regression for swings.boundary circular-import fix."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _cold(code: str) -> None:
    """Run ``code`` in a fresh interpreter with repo root on PYTHONPATH."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"cold import failed ({result.returncode}):\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )


@pytest.mark.parametrize(
    "code",
    [
        "import services.quant_engine.swings.boundary",
        "import services.quant_engine.swings",
        "from services.quant_engine.swings.boundary import build_scan_structure",
        "from services.quant_engine.decision.engine import DecisionEngine",
        "from services.scanner_service.data_loader import DataLoader",
        "from services.scanner_service.signal_builder import SignalBuilder",
    ],
)
def test_cold_imports_succeed(code: str):
    _cold(code)


def test_build_scan_structure_still_works_after_cold_import():
    """Fresh process: build_scan_structure returns ScanStructureInput @ 2.3.0."""
    code = r"""
from services.quant_engine.swings.boundary import (
    SCAN_SWING_VERSION,
    ScanStructureInput,
    build_scan_structure,
)
from tests.swing_detection.fixtures import gold_candles

assert SCAN_SWING_VERSION == "2.3.0"
cs = gold_candles(80, seed=21)
built = build_scan_structure(cs, version=SCAN_SWING_VERSION)
assert isinstance(built, ScanStructureInput)
assert built.swing_version == "2.3.0"
assert built.structure_snapshot is not None
assert isinstance(built.confirmed_swings, tuple)
print("ok", len(built.confirmed_swings), built.structure_snapshot.as_of_index)
"""
    _cold(code)

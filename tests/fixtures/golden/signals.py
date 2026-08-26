"""Golden analytical signal fixtures — regression, not strategy optimization."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tests.swing_detection.fixtures import gold_candles

_GOLDEN_DIR = Path(__file__).resolve().parent


def load_golden_signal(fixture_id: str) -> dict[str, Any]:
    path = _GOLDEN_DIR / f"{fixture_id}.json"
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def build_fixture_candles(spec: dict[str, Any]):
    gen = spec["candle_generator"]
    if gen["name"] != "gold_candles":
        raise ValueError(f"unsupported generator {gen['name']}")
    return gold_candles(int(gen["n"]), trend=float(gen["trend"]), wave=float(gen["wave"]))

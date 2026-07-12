"""Swing Detection Engine v1.1.0 — improved detection with version profile overrides."""

from __future__ import annotations

from shared.types.models import Candle, Timeframe

from swing_engine.config import SwingEngineConfig
from swing_engine.pipeline import run_pipeline

VERSION = "1.1.0"


def detect_v1_1(
    bars: list[Candle],
    *,
    symbol: str | None = None,
    timeframe: Timeframe | None = None,
    config: SwingEngineConfig | None = None,
):
    return run_pipeline(bars, version=VERSION, symbol=symbol, timeframe=timeframe, config=config)

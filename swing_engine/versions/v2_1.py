"""Swing Detection Engine v2.1.0 — reversal-confirmed structural pivots."""

from __future__ import annotations

from shared.types.models import Candle, Timeframe

from swing_engine.config import SwingEngineConfig
from swing_engine.pipeline import run_pipeline

VERSION = "2.1.0"


def detect_v2_1(
    bars: list[Candle],
    *,
    symbol: str | None = None,
    timeframe: Timeframe | None = None,
    config: SwingEngineConfig | None = None,
):
    return run_pipeline(bars, version=VERSION, symbol=symbol, timeframe=timeframe, config=config)

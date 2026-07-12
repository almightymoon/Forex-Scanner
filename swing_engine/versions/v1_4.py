"""Swing Detection Engine v1.4.0 — score-gated confirmation + full dataset suite."""

from __future__ import annotations

from shared.types.models import Candle, Timeframe

from swing_engine.config import SwingEngineConfig
from swing_engine.pipeline import run_pipeline

VERSION = "1.4.0"


def detect_v1_4(
    bars: list[Candle],
    *,
    symbol: str | None = None,
    timeframe: Timeframe | None = None,
    config: SwingEngineConfig | None = None,
):
    return run_pipeline(bars, version=VERSION, symbol=symbol, timeframe=timeframe, config=config)

"""Swing Detection Engine v1.2.0 — adaptive detection, quality score, explainability.

Sprint 3: layers adaptive thresholds (market context), a 0-100 quality score,
and structured explanations on top of the shared pipeline. No new trading
concepts (BOS/CHoCH/liquidity/OB/FVG) are introduced.
"""

from __future__ import annotations

from shared.types.models import Candle, Timeframe

from swing_engine.config import SwingEngineConfig
from swing_engine.pipeline import run_pipeline

VERSION = "1.2.0"


def detect_v1_2(
    bars: list[Candle],
    *,
    symbol: str | None = None,
    timeframe: Timeframe | None = None,
    config: SwingEngineConfig | None = None,
):
    return run_pipeline(bars, version=VERSION, symbol=symbol, timeframe=timeframe, config=config)

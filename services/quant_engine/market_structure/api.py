"""High-level Market Structure Engine facade.

Wraps the causal detector + product projections without rediscovering swings.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from shared.types.models import Candle, Timeframe
from swing_engine.models import DetectedSwing

from services.quant_engine.market_structure.classification import (
    SwingClassificationRecord,
    explain_swing_classifications,
)
from services.quant_engine.market_structure.detector import analyze_structure
from services.quant_engine.market_structure.models import StructureSnapshot
from services.quant_engine.market_structure.regime import (
    StructureRegimeAssessment,
    classify_structure_regime,
)
from services.quant_engine.market_structure.state import (
    MarketStructureStateView,
    build_market_structure_state_view,
)
from services.quant_engine.market_structure.trend_labels import (
    MarketTrendLabel,
    classify_market_trend,
)
from services.quant_engine.swings.boundary import SCAN_SWING_VERSION


@dataclass(frozen=True)
class MarketStructureAnalysis:
    """Complete structure analysis bundle for one symbol/timeframe window."""

    snapshot: StructureSnapshot
    state: MarketStructureStateView
    trend: MarketTrendLabel
    regime: StructureRegimeAssessment
    classifications: tuple[SwingClassificationRecord, ...]
    swing_engine_version: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot": self.snapshot.to_dict(),
            "state": self.state.to_dict(),
            "trend": self.trend.value,
            "regime": self.regime.to_dict(),
            "classifications": [c.to_dict() for c in self.classifications],
            "swing_engine_version": self.swing_engine_version,
            "events": [e.to_dict() for e in self.snapshot.events],
            "bos_events": [
                e.to_dict()
                for e in self.snapshot.events
                if e.event_type.value == "BOS"
            ],
            "choch_events": [
                e.to_dict()
                for e in self.snapshot.events
                if e.event_type.value == "CHOCH"
            ],
        }


def analyze_market_structure(
    candles: list[Candle],
    confirmed_swings: list[DetectedSwing],
    *,
    symbol: str | None = None,
    timeframe: Timeframe | str | None = None,
    as_of_index: int | None = None,
    swing_engine_version: str | None = None,
) -> MarketStructureAnalysis:
    """Run causal structure analysis and return the product-facing bundle.

    ``confirmed_swings`` must already be produced by swing_engine (typically
    ``SCAN_SWING_VERSION`` / v2.3.0). This function never instantiates the
    swing engine.
    """

    snapshot = analyze_structure(
        candles,
        confirmed_swings,
        as_of_index=as_of_index,
    )
    sym = symbol or (candles[-1].symbol if candles else "UNKNOWN")
    tf: Timeframe | str
    if timeframe is not None:
        tf = timeframe
    elif candles:
        tf = candles[-1].timeframe
    else:
        tf = Timeframe.H1
    version = swing_engine_version or SCAN_SWING_VERSION
    trend, regime = classify_market_trend(snapshot)
    state = build_market_structure_state_view(
        snapshot,
        symbol=sym,
        timeframe=tf,
        candles=candles,
        swing_engine_version=version,
        regime=regime,
    )
    classifications = tuple(
        explain_swing_classifications(
            snapshot,
            symbol=sym,
            timeframe=state.timeframe,
            swing_engine_version=version,
        )
    )
    return MarketStructureAnalysis(
        snapshot=snapshot,
        state=state,
        trend=trend,
        regime=regime,
        classifications=classifications,
        swing_engine_version=version,
    )

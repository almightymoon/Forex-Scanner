"""Read-model: current market structure state for downstream consumers.

``StructureSnapshot`` remains the canonical causal detector output.
``MarketStructureStateView`` is a convenience projection matching the
product-facing structure-state contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from shared.types.models import Candle, Timeframe
from swing_engine.models import SwingDirection, SwingScope

from services.quant_engine.market_structure.classification import (
    explain_swing_classifications,
    last_classification,
)
from services.quant_engine.market_structure.models import (
    StructureEvent,
    StructureEventType,
    StructureSnapshot,
)
from services.quant_engine.market_structure.regime import (
    StructureRegimeAssessment,
    classify_structure_regime,
)
from services.quant_engine.market_structure.trend_labels import (
    MarketTrendLabel,
    to_market_trend_label,
)
from services.quant_engine.swings.boundary import SCAN_SWING_VERSION


def _latest_event(
    snapshot: StructureSnapshot,
    event_type: StructureEventType,
    *,
    scope: SwingScope = SwingScope.EXTERNAL,
) -> StructureEvent | None:
    for event in reversed(snapshot.events):
        if event.event_type is event_type and event.scope is scope:
            return event
    return None


@dataclass(frozen=True)
class MarketStructureStateView:
    """Product-facing answer to: what is the current market structure?"""

    symbol: str
    timeframe: str
    trend: MarketTrendLabel
    structure_regime: str
    structure_regime_confidence: float
    external_bias: str
    pending_external_bias: str
    last_swing_high: float | None
    last_swing_low: float | None
    last_high_classification: str | None
    last_low_classification: str | None
    last_bos: dict[str, Any] | None
    last_choch: dict[str, Any] | None
    structure_timestamp: str | None
    as_of_index: int
    swing_engine_version: str
    event_count: int
    classifications: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "trend": self.trend.value,
            "structure_regime": self.structure_regime,
            "structure_regime_confidence": round(self.structure_regime_confidence, 3),
            "external_bias": self.external_bias,
            "pending_external_bias": self.pending_external_bias,
            "last_swing_high": self.last_swing_high,
            "last_swing_low": self.last_swing_low,
            "last_high_classification": self.last_high_classification,
            "last_low_classification": self.last_low_classification,
            "last_bos": self.last_bos,
            "last_choch": self.last_choch,
            "structure_timestamp": self.structure_timestamp,
            "as_of_index": self.as_of_index,
            "swing_engine_version": self.swing_engine_version,
            "event_count": self.event_count,
            "classifications": list(self.classifications),
        }


def build_market_structure_state_view(
    snapshot: StructureSnapshot,
    *,
    symbol: str,
    timeframe: Timeframe | str,
    candles: list[Candle] | None = None,
    swing_engine_version: str | None = None,
    regime: StructureRegimeAssessment | None = None,
) -> MarketStructureStateView:
    """Project a causal snapshot into the product structure-state view."""

    tf = timeframe.value if isinstance(timeframe, Timeframe) else str(timeframe)
    version = swing_engine_version or SCAN_SWING_VERSION
    assessment = regime or classify_structure_regime(snapshot)
    trend = to_market_trend_label(assessment)
    records = explain_swing_classifications(
        snapshot,
        symbol=symbol,
        timeframe=tf,
        swing_engine_version=version,
        scope=SwingScope.EXTERNAL,
    )
    high_cls = last_classification(records, SwingDirection.HIGH)
    low_cls = last_classification(records, SwingDirection.LOW)
    bos = _latest_event(snapshot, StructureEventType.BOS)
    choch = _latest_event(snapshot, StructureEventType.CHOCH)

    ts: str | None = None
    if candles and 0 <= snapshot.as_of_index < len(candles):
        raw = candles[snapshot.as_of_index].timestamp
        ts = raw.isoformat() if isinstance(raw, datetime) else str(raw)
    elif snapshot.events:
        ts = snapshot.events[-1].break_timestamp.isoformat()

    return MarketStructureStateView(
        symbol=symbol,
        timeframe=tf,
        trend=trend,
        structure_regime=assessment.regime.value,
        structure_regime_confidence=assessment.confidence,
        external_bias=snapshot.external_bias.value,
        pending_external_bias=snapshot.pending_external_bias.value,
        last_swing_high=snapshot.latest_external_high,
        last_swing_low=snapshot.latest_external_low,
        last_high_classification=high_cls.value if high_cls else None,
        last_low_classification=low_cls.value if low_cls else None,
        last_bos=bos.to_dict() if bos else None,
        last_choch=choch.to_dict() if choch else None,
        structure_timestamp=ts,
        as_of_index=snapshot.as_of_index,
        swing_engine_version=version,
        event_count=len(snapshot.events),
        classifications=tuple(r.to_dict() for r in records),
    )

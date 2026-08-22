"""Multi-timeframe structure bias from Market Structure Engine v1.

Computes per-TF ``external_bias`` via confirmed swings + ``analyze_structure``.
Used by the live DataLoader and offline smoke/studio paths.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from shared.types.models import Candle, Timeframe, TrendDirection

from services.quant_engine.market_structure.aggregate import aggregate_candles
from services.quant_engine.market_structure.detector import analyze_structure
from services.quant_engine.market_structure.models import StructureSnapshot
from services.quant_engine.market_structure.regime import (
    StructureRegimeAssessment,
    classify_structure_regime,
)
from services.quant_engine.swings.boundary import SCAN_SWING_VERSION, obtain_confirmed_swings


@dataclass(frozen=True)
class TimeframeStructureBias:
    timeframe: str
    bias: TrendDirection
    pending_bias: TrendDirection
    regime: str
    regime_confidence: float
    event_count: int
    swing_count: int
    source: str  # "structure" | "insufficient"

    def to_dict(self) -> dict[str, Any]:
        return {
            "timeframe": self.timeframe,
            "bias": self.bias.value,
            "pending_bias": self.pending_bias.value,
            "regime": self.regime,
            "regime_confidence": round(self.regime_confidence, 3),
            "event_count": self.event_count,
            "swing_count": self.swing_count,
            "source": self.source,
        }


@dataclass(frozen=True)
class MTFStructureBiasResult:
    biases: dict[str, TimeframeStructureBias]
    trends: dict[str, TrendDirection]
    snapshots: dict[str, StructureSnapshot]

    def to_dict(self) -> dict[str, Any]:
        return {
            "biases": {k: v.to_dict() for k, v in sorted(self.biases.items())},
            "trends": {k: v.value for k, v in sorted(self.trends.items())},
        }


def structure_bias_for_candles(
    candles: list[Candle],
    *,
    version: str = SCAN_SWING_VERSION,
    min_bars: int = 50,
) -> tuple[TimeframeStructureBias, StructureSnapshot | None]:
    """Run confirmed swings + structure on one TF series."""

    tf = candles[0].timeframe.value if candles else "H1"
    if len(candles) < min_bars:
        return (
            TimeframeStructureBias(
                timeframe=tf,
                bias=TrendDirection.RANGING,
                pending_bias=TrendDirection.RANGING,
                regime="ranging",
                regime_confidence=0.0,
                event_count=0,
                swing_count=0,
                source="insufficient",
            ),
            None,
        )

    swings = obtain_confirmed_swings(candles, version=version)
    snapshot = analyze_structure(candles, swings)
    assessment: StructureRegimeAssessment = classify_structure_regime(snapshot)
    return (
        TimeframeStructureBias(
            timeframe=tf,
            bias=snapshot.external_bias,
            pending_bias=snapshot.pending_external_bias,
            regime=assessment.regime.value,
            regime_confidence=assessment.confidence,
            event_count=len(snapshot.events),
            swing_count=len(swings),
            source="structure",
        ),
        snapshot,
    )


def compute_mtf_structure_bias(
    bars_by_timeframe: dict[str, list[Candle]],
    *,
    version: str = SCAN_SWING_VERSION,
    min_bars: int = 50,
) -> MTFStructureBiasResult:
    """Compute structure bias for each provided TF candle series."""

    biases: dict[str, TimeframeStructureBias] = {}
    trends: dict[str, TrendDirection] = {}
    snapshots: dict[str, StructureSnapshot] = {}

    for _tf_name, candles in sorted(bars_by_timeframe.items()):
        if not candles:
            continue
        bias, snapshot = structure_bias_for_candles(
            candles, version=version, min_bars=min_bars
        )
        key = candles[0].timeframe.value
        biases[key] = bias
        if snapshot is not None:
            snapshots[key] = snapshot
        if bias.source == "structure" and bias.bias is not TrendDirection.RANGING:
            trends[key] = bias.bias

    return MTFStructureBiasResult(biases=biases, trends=trends, snapshots=snapshots)


def compute_mtf_structure_bias_from_h1(
    h1_candles: list[Candle],
    *,
    higher_tfs: tuple[Timeframe, ...] = (Timeframe.H4, Timeframe.D1),
    version: str = SCAN_SWING_VERSION,
    min_bars: int = 50,
    include_h1: bool = True,
) -> MTFStructureBiasResult:
    """Offline helper: aggregate H1 → H4/D1 and compute structure biases."""

    bars: dict[str, list[Candle]] = {}
    if include_h1 and h1_candles:
        bars["H1"] = list(h1_candles)
    for tf in higher_tfs:
        agg = aggregate_candles(h1_candles, tf)
        if agg:
            bars[tf.value] = agg
    return compute_mtf_structure_bias(bars, version=version, min_bars=min_bars)

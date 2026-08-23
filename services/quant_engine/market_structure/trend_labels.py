"""Product-facing market-trend labels (BULLISH / BEARISH / RANGING / UNDEFINED).

These are a stable external vocabulary mapped from the richer internal
``StructureRegime`` enum. Internal detector/regime logic is unchanged.
"""

from __future__ import annotations

from enum import Enum

from services.quant_engine.market_structure.regime import (
    StructureRegime,
    StructureRegimeAssessment,
    classify_structure_regime,
)
from services.quant_engine.market_structure.models import StructureSnapshot


class MarketTrendLabel(str, Enum):
    """Coarse structure trend for downstream consumers.

    UNDEFINED = insufficient or ambiguous evidence (do not force a side).
    """

    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    RANGING = "RANGING"
    UNDEFINED = "UNDEFINED"


def to_market_trend_label(assessment: StructureRegimeAssessment) -> MarketTrendLabel:
    """Map internal regime assessment → product trend label."""

    if assessment.regime is StructureRegime.TRENDING_BULLISH:
        return MarketTrendLabel.BULLISH
    if assessment.regime is StructureRegime.TRENDING_BEARISH:
        return MarketTrendLabel.BEARISH
    if assessment.regime is StructureRegime.RANGING:
        # Empty / no-snapshot stays UNDEFINED; active ranging stays RANGING.
        reasons = set(assessment.reasons)
        if "No structure snapshot" in reasons:
            return MarketTrendLabel.UNDEFINED
        if assessment.confidence <= 0.0:
            return MarketTrendLabel.UNDEFINED
        if (
            "No committed external trend" in reasons
            and int(assessment.metadata.get("event_count", 0) or 0) == 0
            and int(assessment.metadata.get("external_relation_count", 0) or 0) == 0
            and int(assessment.metadata.get("bullish_relations", 0) or 0) == 0
            and int(assessment.metadata.get("bearish_relations", 0) or 0) == 0
        ):
            return MarketTrendLabel.UNDEFINED
        return MarketTrendLabel.RANGING
    # REVERSAL_PENDING / TRANSITIONAL — do not force BULLISH/BEARISH.
    return MarketTrendLabel.UNDEFINED


def classify_market_trend(
    snapshot: StructureSnapshot | None,
) -> tuple[MarketTrendLabel, StructureRegimeAssessment]:
    """Classify product trend + full internal assessment from a causal snapshot."""

    assessment = classify_structure_regime(snapshot)
    return to_market_trend_label(assessment), assessment

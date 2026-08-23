"""Structure regime classification from Market Structure Engine v1 snapshots.

First consumer of ``StructureSnapshot`` for trend/regime-style filtering.
Uses only causal snapshot fields (bias, pending, relations, events) — no
lookahead and no swing rediscovery.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from shared.types.models import TrendDirection
from swing_engine.models import SwingScope

from services.quant_engine.market_structure.models import (
    StructureEventType,
    StructureRelation,
    StructureSnapshot,
)


class StructureRegime(str, Enum):
    TRENDING_BULLISH = "trending_bullish"
    TRENDING_BEARISH = "trending_bearish"
    REVERSAL_PENDING = "reversal_pending"
    RANGING = "ranging"
    TRANSITIONAL = "transitional"


@dataclass(frozen=True)
class StructureRegimeAssessment:
    regime: StructureRegime
    confidence: float
    external_bias: TrendDirection
    pending_external_bias: TrendDirection
    internal_bias: TrendDirection
    reasons: tuple[str, ...]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        from services.quant_engine.market_structure.trend_labels import (
            to_market_trend_label,
        )

        return {
            "regime": self.regime.value,
            "trend": to_market_trend_label(self).value,
            "confidence": round(self.confidence, 3),
            "external_bias": self.external_bias.value,
            "pending_external_bias": self.pending_external_bias.value,
            "internal_bias": self.internal_bias.value,
            "reasons": list(self.reasons),
            "metadata": dict(sorted(self.metadata.items())),
        }


def classify_structure_regime(
    snapshot: StructureSnapshot | None,
) -> StructureRegimeAssessment:
    """Classify a coarse structure regime from a causal StructureSnapshot."""

    if snapshot is None:
        return StructureRegimeAssessment(
            regime=StructureRegime.RANGING,
            confidence=0.0,
            external_bias=TrendDirection.RANGING,
            pending_external_bias=TrendDirection.RANGING,
            internal_bias=TrendDirection.RANGING,
            reasons=("No structure snapshot",),
            metadata={},
        )

    reasons: list[str] = []
    ext = snapshot.external_bias
    pending = snapshot.pending_external_bias
    internal = snapshot.internal_bias

    ext_relations = [
        r
        for r in snapshot.swing_relations
        if r.scope is SwingScope.EXTERNAL
        and r.relation
        not in (StructureRelation.UNKNOWN, StructureRelation.EQUAL_HIGH, StructureRelation.EQUAL_LOW)
    ]
    bullish_seq = sum(
        1
        for r in ext_relations
        if r.relation in (StructureRelation.HH, StructureRelation.HL)
    )
    bearish_seq = sum(
        1
        for r in ext_relations
        if r.relation in (StructureRelation.LH, StructureRelation.LL)
    )
    last_event = snapshot.events[-1] if snapshot.events else None
    choch_pending = pending is not TrendDirection.RANGING

    if choch_pending:
        reasons.append(
            f"Pending external reversal toward {pending.value}"
        )
        if last_event and last_event.event_type is StructureEventType.CHOCH:
            reasons.append(f"Latest event CHOCH ({last_event.event_id})")
        confidence = 0.55 + min(0.25, 0.05 * len(snapshot.events))
        return StructureRegimeAssessment(
            regime=StructureRegime.REVERSAL_PENDING,
            confidence=min(0.9, confidence),
            external_bias=ext,
            pending_external_bias=pending,
            internal_bias=internal,
            reasons=tuple(reasons),
            metadata={
                "event_count": len(snapshot.events),
                "external_relation_count": len(ext_relations),
            },
        )

    if ext is TrendDirection.BULLISH and bullish_seq >= bearish_seq:
        reasons.append("External bias bullish")
        if bullish_seq:
            reasons.append(f"External HH/HL relations={bullish_seq}")
        if last_event and last_event.is_continuation:
            reasons.append("Latest event is continuation BOS")
        confidence = 0.5 + min(0.35, 0.08 * max(bullish_seq, 1))
        if internal is TrendDirection.BULLISH:
            confidence += 0.05
            reasons.append("Internal bias agrees bullish")
        elif internal is TrendDirection.BEARISH:
            confidence -= 0.08
            reasons.append("Internal bias disagrees (bearish)")
        return StructureRegimeAssessment(
            regime=StructureRegime.TRENDING_BULLISH,
            confidence=min(0.95, max(0.35, confidence)),
            external_bias=ext,
            pending_external_bias=pending,
            internal_bias=internal,
            reasons=tuple(reasons),
            metadata={
                "event_count": len(snapshot.events),
                "bullish_relations": bullish_seq,
                "bearish_relations": bearish_seq,
            },
        )

    if ext is TrendDirection.BEARISH and bearish_seq >= bullish_seq:
        reasons.append("External bias bearish")
        if bearish_seq:
            reasons.append(f"External LH/LL relations={bearish_seq}")
        if last_event and last_event.is_continuation:
            reasons.append("Latest event is continuation BOS")
        confidence = 0.5 + min(0.35, 0.08 * max(bearish_seq, 1))
        if internal is TrendDirection.BEARISH:
            confidence += 0.05
            reasons.append("Internal bias agrees bearish")
        elif internal is TrendDirection.BULLISH:
            confidence -= 0.08
            reasons.append("Internal bias disagrees (bullish)")
        return StructureRegimeAssessment(
            regime=StructureRegime.TRENDING_BEARISH,
            confidence=min(0.95, max(0.35, confidence)),
            external_bias=ext,
            pending_external_bias=pending,
            internal_bias=internal,
            reasons=tuple(reasons),
            metadata={
                "event_count": len(snapshot.events),
                "bullish_relations": bullish_seq,
                "bearish_relations": bearish_seq,
            },
        )

    if ext is TrendDirection.RANGING and (bullish_seq or bearish_seq):
        reasons.append("External ranging with mixed relations")
        return StructureRegimeAssessment(
            regime=StructureRegime.TRANSITIONAL,
            confidence=0.4,
            external_bias=ext,
            pending_external_bias=pending,
            internal_bias=internal,
            reasons=tuple(reasons),
            metadata={
                "event_count": len(snapshot.events),
                "bullish_relations": bullish_seq,
                "bearish_relations": bearish_seq,
            },
        )

    reasons.append("No committed external trend")
    return StructureRegimeAssessment(
        regime=StructureRegime.RANGING,
        confidence=0.45 if not snapshot.events else 0.35,
        external_bias=ext,
        pending_external_bias=pending,
        internal_bias=internal,
        reasons=tuple(reasons),
        metadata={
            "event_count": len(snapshot.events),
            "external_relation_count": len(ext_relations),
            "bullish_relations": bullish_seq,
            "bearish_relations": bearish_seq,
        },
    )

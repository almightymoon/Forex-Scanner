"""BOS/CHoCH-ready structure metadata attached to every confirmed swing."""

from __future__ import annotations

from swing_engine.models import DetectedSwing, SwingDirection, SwingScope, SwingTier, TrendBias


def swing_id(swing: DetectedSwing) -> str:
    return f"{swing.direction.value}:{swing.pivot_index}"


def enrich_structure_metadata(swings: list[DetectedSwing]) -> list[DetectedSwing]:
    """Attach stable IDs and structural context for downstream market-structure layers."""
    last: dict[SwingDirection, DetectedSwing | None] = {
        SwingDirection.HIGH: None,
        SwingDirection.LOW: None,
    }
    for i, s in enumerate(swings):
        opp = SwingDirection.LOW if s.direction == SwingDirection.HIGH else SwingDirection.HIGH
        prev_same = last[s.direction]
        prev_opp = last[opp]
        leg_start = prev_opp.pivot_index if prev_opp else 0
        trend = _trend_state(prev_opp, prev_same, s)

        s.metadata.update({
            "swing_id": swing_id(s),
            "leg_id": f"leg_{i}",
            "leg_start_index": leg_start,
            "leg_end_index": s.pivot_index,
            "leg_bars": s.pivot_index - leg_start,
            "prev_same_swing_id": swing_id(prev_same) if prev_same else None,
            "prev_opposite_swing_id": swing_id(prev_opp) if prev_opp else None,
            "prev_same_price": prev_same.price if prev_same else None,
            "prev_opposite_price": prev_opp.price if prev_opp else None,
            "trend_state": trend.value,
            "is_major": s.tier == SwingTier.MAJOR,
            "is_external": s.scope == SwingScope.EXTERNAL,
            "is_internal": s.scope == SwingScope.INTERNAL,
            "confirmation_candle_index": s.confirmation_index,
            "pivot_candle_index": s.pivot_index,
            "hierarchy_state": (
                s.hierarchy_state.value if s.hierarchy_state is not None else None
            ),
            "hierarchy_confirmation_candle_index": s.hierarchy_confirmation_index,
            "hierarchy_revision_candle_index": s.hierarchy_revision_index,
        })
        last[s.direction] = s
    return swings


def _trend_state(
    prev_opp: DetectedSwing | None,
    prev_same: DetectedSwing | None,
    current: DetectedSwing,
) -> TrendBias:
    if not prev_opp or not prev_same:
        return TrendBias.RANGING
    if current.direction == SwingDirection.HIGH:
        if current.price > prev_opp.price and prev_same.price > prev_opp.price:
            return TrendBias.BULLISH
        if current.price < prev_opp.price:
            return TrendBias.BEARISH
    else:
        if current.price < prev_opp.price and prev_same.price < prev_opp.price:
            return TrendBias.BEARISH
        if current.price > prev_opp.price:
            return TrendBias.BULLISH
    return TrendBias.RANGING

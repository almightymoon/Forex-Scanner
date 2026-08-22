"""Map Market Structure Engine v1 snapshots into MarketFeatures fields.

The detector contract is unchanged. This module only translates StructureSnapshot
(+ optional confirmed swings) into the normalized feature dict / legacy-compatible
MarketStructureState and TrendContext objects consumed downstream.
"""

from __future__ import annotations

from shared.types.models import Candle, TrendDirection
from swing_engine.models import DetectedSwing, SwingScope

from services.quant_engine.market_structure.models import (
    StructureEvent,
    StructureRelation,
    StructureSnapshot,
)
from services.quant_engine.swing_analysis import (
    MarketStructureState,
    SwingPoint,
    TrendContext,
)


def _event_name(event: StructureEvent | None) -> str | None:
    if event is None:
        return None
    return event.event_type.value.lower()


def _bos_kind_from_snapshot(snapshot: StructureSnapshot) -> str:
    """Prefer latest external event; fall back to latest internal; else external."""

    if not snapshot.events:
        if snapshot.external_bias is not TrendDirection.RANGING:
            return "external"
        if snapshot.internal_bias is not TrendDirection.RANGING:
            return "internal"
        return "external"
    last = snapshot.events[-1]
    return "external" if last.scope is SwingScope.EXTERNAL else "internal"


def _sequence_from_snapshot(snapshot: StructureSnapshot) -> list[str]:
    """Ordered structural relation labels (external track preferred, then internal)."""

    seq: list[str] = []
    for scope in (SwingScope.EXTERNAL, SwingScope.INTERNAL):
        for rel in snapshot.swing_relations:
            if rel.scope is not scope:
                continue
            if rel.relation is StructureRelation.UNKNOWN:
                continue
            seq.append(rel.relation.value)
    return seq


def _swings_to_points(confirmed_swings: list[DetectedSwing]) -> list[SwingPoint]:
    points: list[SwingPoint] = []
    for swing in confirmed_swings:
        kind = swing.direction.value.lower()
        points.append(
            SwingPoint(
                index=int(swing.pivot_index),
                price=float(swing.price),
                kind=kind,
                strength=float(swing.score),
                displacement_atr=float(swing.metadata.get("leg_atr", 0.0) or 0.0),
            )
        )
    points.sort(key=lambda p: (p.index, p.kind))
    return points


def latest_structure_event(snapshot: StructureSnapshot) -> StructureEvent | None:
    if not snapshot.events:
        return None
    return snapshot.events[-1]


def build_market_structure_state(
    snapshot: StructureSnapshot,
    confirmed_swings: list[DetectedSwing] | None = None,
) -> MarketStructureState:
    """Legacy-compatible structure state derived from a v1 snapshot."""

    swings = _swings_to_points(list(confirmed_swings or []))
    highs = [s for s in swings if s.kind == "high"]
    lows = [s for s in swings if s.kind == "low"]
    last = latest_structure_event(snapshot)
    strengths = [s.strength for s in swings[-6:]]
    avg = sum(strengths) / len(strengths) if strengths else 0.0

    return MarketStructureState(
        swings=swings,
        swing_highs=highs,
        swing_lows=lows,
        direction=snapshot.external_bias,
        last_event=_event_name(last),
        event_direction=(
            None
            if last is None
            else (
                "buy"
                if last.direction is TrendDirection.BULLISH
                else "sell"
                if last.direction is TrendDirection.BEARISH
                else None
            )
        ),
        bos_kind=_bos_kind_from_snapshot(snapshot),
        continuation=True if last is None else bool(last.is_continuation),
        swing_strength_avg=avg,
        sequence=_sequence_from_snapshot(snapshot),
    )


def build_trend_context_from_structure(
    snapshot: StructureSnapshot,
    candles: list[Candle],
    ema20: float | None,
    ema50: float | None,
    *,
    confirmed_swings: list[DetectedSwing] | None = None,
) -> TrendContext:
    """TrendContext using v1 structure for bias; candle/EMA for compression/pullback.

    Does not call legacy analyze_market_structure / build_zigzag_swings.
    """

    ctx = TrendContext()
    structure = build_market_structure_state(snapshot, confirmed_swings)
    ctx.structure = structure
    ctx.swing_highs = structure.swing_highs[-4:]
    ctx.swing_lows = structure.swing_lows[-4:]
    ctx.direction = snapshot.external_bias

    if snapshot.external_bias is not TrendDirection.RANGING:
        avg_str = structure.swing_strength_avg / 100 if structure.swing_strength_avg else 0.5
        pending = snapshot.pending_external_bias is not TrendDirection.RANGING
        base = 0.35 + avg_str * 0.55
        if pending:
            base *= 0.85
        ctx.strength = min(1.0, max(0.0, base))
        if structure.continuation:
            ctx.reasons.append(
                f"Swing structure: {' · '.join(structure.sequence) or snapshot.external_bias.value} — trend continuation"
            )
        elif structure.last_event == "choch":
            ctx.reasons.append("CHoCH detected — potential trend reversal")
        else:
            label = " · ".join(structure.sequence) if structure.sequence else snapshot.external_bias.value
            ctx.reasons.append(f"Swing structure: {label}")

    if len(candles) >= 20:
        recent = candles[-20:]
        ranges = [c.high - c.low for c in recent]
        avg_range = sum(ranges[:-5]) / max(len(ranges[:-5]), 1)
        last_range = sum(ranges[-5:]) / 5
        if last_range < avg_range * 0.7:
            ctx.compression = True
            ctx.reasons.append("Volatility compression — coiling before expansion")
        elif last_range > avg_range * 1.3:
            ctx.expansion = True
            ctx.reasons.append("Volatility expansion — trend impulse active")

    price = candles[-1].close if candles else 0.0
    if ema20 and ema50 and ctx.direction == TrendDirection.BULLISH:
        if price < ema20 and price > ema50:
            ctx.pullback = True
            ctx.reasons.append("Healthy bullish pullback to EMA zone")
    elif ema20 and ema50 and ctx.direction == TrendDirection.BEARISH:
        if price > ema20 and price < ema50:
            ctx.pullback = True
            ctx.reasons.append("Healthy bearish pullback to EMA zone")

    bars_in_trend = 0
    for c in reversed(candles[-30:]):
        if ema20 and ema50:
            if ctx.direction == TrendDirection.BULLISH and c.close > ema50:
                bars_in_trend += 1
            elif ctx.direction == TrendDirection.BEARISH and c.close < ema50:
                bars_in_trend += 1
            else:
                break
    if bars_in_trend > 20:
        ctx.maturity = "mature"
        ctx.reasons.append("Mature trend — watch for exhaustion")
    elif bars_in_trend > 8:
        ctx.maturity = "established"
    else:
        ctx.maturity = "developing"

    return ctx


def structure_snapshot_to_features(
    snapshot: StructureSnapshot,
    *,
    confirmed_swings: list[DetectedSwing] | None = None,
) -> dict:
    """Translate a StructureSnapshot into MarketFeatures-compatible fields."""

    last = latest_structure_event(snapshot)
    swings = list(confirmed_swings or [])
    strengths = [float(s.score) for s in swings]
    avg = sum(strengths) / len(strengths) if strengths else 0.0
    structure = build_market_structure_state(snapshot, swings)

    return {
        "structure_snapshot": snapshot,
        "structure": structure,
        "external_bias": snapshot.external_bias,
        "pending_external_bias": snapshot.pending_external_bias,
        "internal_bias": snapshot.internal_bias,
        "pending_internal_bias": snapshot.pending_internal_bias,
        "latest_external_high": snapshot.latest_external_high,
        "latest_external_low": snapshot.latest_external_low,
        "latest_internal_high": snapshot.latest_internal_high,
        "latest_internal_low": snapshot.latest_internal_low,
        "structural_sequence": list(structure.sequence),
        "structure_event_ids": [e.event_id for e in snapshot.events],
        "latest_structure_event_id": None if last is None else last.event_id,
        "latest_bos_choch": None if last is None else last.to_dict(),
        "bos_kind": structure.bos_kind,
        "last_structure_event": structure.last_event,
        "structure_continuation": structure.continuation,
        "trend_direction": snapshot.external_bias,
        "swing_count": len(swings),
        "swing_strength_avg": avg,
        "structure_metadata": {
            "detector": "market_structure_v1",
            "as_of_index": snapshot.as_of_index,
            "event_count": len(snapshot.events),
            "relation_count": len(snapshot.swing_relations),
            **dict(snapshot.metadata),
        },
    }

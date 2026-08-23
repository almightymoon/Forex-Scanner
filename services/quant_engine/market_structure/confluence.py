"""Setup confluence scoring from StructureSnapshot + SMC patterns.

Second StructureSnapshot consumer: measures agreement between external
structure bias/events and OB / FVG / liquidity patterns. Causal only —
no lookahead and no swing rediscovery.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from shared.types.models import SMCPattern, SignalDirection, TrendDirection

from services.quant_engine.features.types import MarketFeatures
from services.quant_engine.market_structure.models import StructureEventType, StructureSnapshot
from services.quant_engine.market_structure.regime import StructureRegime


@dataclass(frozen=True)
class SetupConfluenceAssessment:
    score: float  # 0..1
    aligned: bool
    direction_hint: SignalDirection
    factors: tuple[str, ...]
    blockers: tuple[str, ...]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": round(self.score, 3),
            "aligned": self.aligned,
            "direction_hint": self.direction_hint.value,
            "factors": list(self.factors),
            "blockers": list(self.blockers),
            "metadata": dict(sorted(self.metadata.items())),
        }


def _pattern_side(pattern: SMCPattern) -> SignalDirection | None:
    if pattern.direction in (SignalDirection.BUY, SignalDirection.SELL):
        return pattern.direction
    return None


def assess_setup_confluence(
    *,
    features: MarketFeatures | None,
    patterns: list[SMCPattern],
    snapshot: StructureSnapshot | None = None,
    proposed_direction: SignalDirection | None = None,
) -> SetupConfluenceAssessment:
    """Score confluence of structure regime/events with SMC setup patterns."""

    snap = snapshot or (features.structure_snapshot if features else None)
    regime = (features.structure_regime if features else None) or StructureRegime.RANGING.value
    external = (
        features.external_bias if features else TrendDirection.RANGING
    )
    pending = (
        features.pending_external_bias if features else TrendDirection.RANGING
    )

    factors: list[str] = []
    blockers: list[str] = []
    points = 0.0
    max_points = 0.0

    # Structure bias contributes when committed.
    max_points += 2.0
    hint = SignalDirection.NEUTRAL
    if external is TrendDirection.BULLISH:
        hint = SignalDirection.BUY
        points += 2.0
        factors.append("External bias bullish")
    elif external is TrendDirection.BEARISH:
        hint = SignalDirection.SELL
        points += 2.0
        factors.append("External bias bearish")
    else:
        blockers.append("No committed external bias")

    # Regime quality.
    max_points += 1.5
    if regime in (
        StructureRegime.TRENDING_BULLISH.value,
        StructureRegime.TRENDING_BEARISH.value,
    ):
        points += 1.5
        factors.append(f"Regime {regime}")
    elif regime == StructureRegime.REVERSAL_PENDING.value:
        points += 0.4
        blockers.append("Reversal pending — setup risk elevated")
    elif regime == StructureRegime.TRANSITIONAL.value:
        points += 0.6
        factors.append("Transitional regime")
    else:
        blockers.append("Ranging structure regime")

    # Latest structure event agreement.
    max_points += 1.5
    last = None
    if snap and snap.events:
        last = snap.events[-1]
        if last.event_type is StructureEventType.BOS and last.is_continuation:
            points += 1.5
            factors.append("Continuation BOS")
        elif last.event_type is StructureEventType.BOS:
            points += 1.0
            factors.append("BOS present")
        elif last.event_type is StructureEventType.CHOCH:
            points += 0.3
            blockers.append("Latest event is CHOCH")
    else:
        blockers.append("No structure events")

    # Pattern confluence with structure side.
    setup_types = {
        "order_block",
        "fvg",
        "liquidity_sweep",
        "equal_highs",
        "equal_lows",
        "bos",
        "choch",
    }
    setup_patterns = [p for p in patterns if p.pattern_type in setup_types]
    max_points += 3.0
    agreeing = 0
    conflicting = 0
    for p in setup_patterns:
        side = _pattern_side(p)
        if side is None or hint is SignalDirection.NEUTRAL:
            continue
        if side is hint:
            agreeing += 1
        elif side in (SignalDirection.BUY, SignalDirection.SELL):
            conflicting += 1

    if agreeing:
        points += min(3.0, 1.0 * agreeing)
        factors.append(f"{agreeing} setup pattern(s) agree with structure")
    if conflicting:
        points -= min(1.5, 0.75 * conflicting)
        blockers.append(f"{conflicting} setup pattern(s) conflict with structure")

    # Typed liquidity map (continuation vs stop-hunt).
    liquidity_meta: dict[str, Any] = {}
    if features is not None and getattr(features, "liquidity_map", None):
        from services.quant_engine.liquidity.models import SweepQuality

        liq = features.liquidity_map
        liquidity_meta = liq.to_dict() if hasattr(liq, "to_dict") else {}
        max_points += 1.5
        cont = sum(1 for s in liq.sweeps if s.quality is SweepQuality.CONTINUATION)
        hunts = sum(1 for s in liq.sweeps if s.quality is SweepQuality.STOP_HUNT)
        if cont:
            points += min(1.5, 0.75 * cont)
            factors.append(f"{cont} continuation liquidity sweep(s)")
        if hunts:
            points -= min(1.0, 0.5 * hunts)
            blockers.append(f"{hunts} stop-hunt liquidity sweep(s)")
        equal_buy = sum(1 for lv in liq.levels if lv.kind.value == "equal_lows")
        equal_sell = sum(1 for lv in liq.levels if lv.kind.value == "equal_highs")
        if hint is SignalDirection.BUY and equal_buy:
            points += 0.25
            factors.append("Equal lows pool supports buy bias")
        elif hint is SignalDirection.SELL and equal_sell:
            points += 0.25
            factors.append("Equal highs pool supports sell bias")

    # Pending reversal soft-block when proposing with the old bias.
    if pending is not TrendDirection.RANGING:
        max_points += 0.5
        points += 0.1
        blockers.append(f"Pending reversal toward {pending.value}")

    # Proposed direction agreement (if provided).
    if proposed_direction in (SignalDirection.BUY, SignalDirection.SELL):
        max_points += 1.0
        if hint is SignalDirection.NEUTRAL:
            points += 0.2
        elif proposed_direction is hint:
            points += 1.0
            factors.append("Proposed direction agrees with external bias")
        else:
            points -= 0.5
            blockers.append("Proposed direction fights external bias")

    score = 0.0 if max_points <= 0 else max(0.0, min(1.0, points / max_points))
    aligned = (
        score >= 0.55
        and hint is not SignalDirection.NEUTRAL
        and regime != StructureRegime.REVERSAL_PENDING.value
        and not (proposed_direction in (SignalDirection.BUY, SignalDirection.SELL) and proposed_direction is not hint and hint is not SignalDirection.NEUTRAL)
    )

    return SetupConfluenceAssessment(
        score=score,
        aligned=aligned,
        direction_hint=hint,
        factors=tuple(factors),
        blockers=tuple(blockers),
        metadata={
            "regime": regime,
            "agreeing_patterns": agreeing,
            "conflicting_patterns": conflicting,
            "pending_external_bias": pending.value,
            "last_event_id": None if last is None else last.event_id,
            "liquidity": liquidity_meta,
        },
    )

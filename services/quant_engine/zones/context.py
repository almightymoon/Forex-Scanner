"""Explainable zone context derived from canonical pipeline facts.

Not a detector — consumes StructureSnapshot, LiquiditySnapshot, and as-of price/ATR.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

from shared.types.models import SignalDirection, TrendDirection

from services.quant_engine.liquidity.models import (
    LiquiditySide,
    LiquiditySnapshot,
    PoolStatus,
)
from services.quant_engine.market_structure.models import StructureSnapshot

ZONE_RANKING_VERSION = "1.0.0"


class Alignment(str, Enum):
    ALIGNED = "ALIGNED"
    OPPOSED = "OPPOSED"
    NEUTRAL = "NEUTRAL"
    UNDEFINED = "UNDEFINED"


class LiquidityRelation(str, Enum):
    ASSOCIATED_SWEEP = "ASSOCIATED_SWEEP"
    NEAR_RELEVANT = "NEAR_RELEVANT"
    NONE = "NONE"
    OPPOSING = "OPPOSING"


class _ZoneLike(Protocol):
    zone_id: str
    direction: SignalDirection
    created_index: int
    age_bars: int
    status: Any


def _align(direction: SignalDirection, bias: TrendDirection | None) -> Alignment:
    if bias is None:
        return Alignment.UNDEFINED
    if bias is TrendDirection.RANGING:
        return Alignment.NEUTRAL
    if direction is SignalDirection.BUY:
        if bias is TrendDirection.BULLISH:
            return Alignment.ALIGNED
        if bias is TrendDirection.BEARISH:
            return Alignment.OPPOSED
    if direction is SignalDirection.SELL:
        if bias is TrendDirection.BEARISH:
            return Alignment.ALIGNED
        if bias is TrendDirection.BULLISH:
            return Alignment.OPPOSED
    return Alignment.UNDEFINED


def _zone_bounds(zone: Any) -> tuple[float, float]:
    if hasattr(zone, "lower_bound"):
        return float(zone.lower_bound), float(zone.upper_bound)
    return float(zone.price_low), float(zone.price_high)


def _distance_to_zone(price: float, lo: float, hi: float) -> tuple[float, bool]:
    """Absolute distance to zone; 0 when price is inside [lo, hi]."""
    if lo > hi:
        lo, hi = hi, lo
    if lo <= price <= hi:
        return 0.0, True
    if price < lo:
        return lo - price, False
    return price - hi, False


def _liquidity_relation(
    *,
    direction: SignalDirection,
    lo: float,
    hi: float,
    mid: float,
    liquidity: LiquiditySnapshot | None,
    atr: float,
) -> tuple[LiquidityRelation, str | None, str | None]:
    """Relate zone to LiquiditySnapshot pools/sweeps only (no re-detection)."""
    if liquidity is None:
        return LiquidityRelation.NONE, None, None

    near_tol = max(atr * 0.5, (hi - lo) * 0.5, 1e-9) if atr > 0 else max((hi - lo) * 0.5, 1e-9)

    def _near(level: float) -> bool:
        if lo - near_tol <= level <= hi + near_tol:
            return True
        return abs(level - mid) <= near_tol

    # Sweeps first (stronger association).
    for sweep in liquidity.recent_sweeps:
        if _near(float(sweep.level_price)):
            return (
                LiquidityRelation.ASSOCIATED_SWEEP,
                sweep.pool_id,
                sweep.sweep_id,
            )

    nearest: tuple[float, Any] | None = None
    for pool in liquidity.pools:
        if pool.status is not PoolStatus.ACTIVE:
            continue
        d = abs(float(pool.price) - mid)
        if not _near(float(pool.price)):
            continue
        if nearest is None or d < nearest[0]:
            nearest = (d, pool)

    if nearest is None:
        return LiquidityRelation.NONE, None, None

    pool = nearest[1]
    # Opposing supply/demand: bullish zone next to sell-side pool, or bearish next to buy-side.
    if direction is SignalDirection.BUY and pool.side is LiquiditySide.SELL_SIDE:
        return LiquidityRelation.OPPOSING, pool.pool_id, None
    if direction is SignalDirection.SELL and pool.side is LiquiditySide.BUY_SIDE:
        return LiquidityRelation.OPPOSING, pool.pool_id, None
    return LiquidityRelation.NEAR_RELEVANT, pool.pool_id, None


@dataclass(frozen=True)
class ZoneRankContext:
    """Deterministic explainable context for one zone at one as-of index."""

    zone_id: str
    structure_alignment: Alignment
    trend_alignment: Alignment
    liquidity_relation: LiquidityRelation
    distance_to_price: float
    distance_atr: float
    price_inside_zone: bool
    freshness_bars: int
    mitigation_state: str
    timeframe: str
    reference_price: float
    liquidity_pool_id: str | None = None
    liquidity_sweep_id: str | None = None
    htf_trend: str | None = None
    htf_trend_tf: str | None = None
    trend_source: str = "structure_external_bias"
    reasons: tuple[str, ...] = ()
    ranking_version: str = ZONE_RANKING_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "zone_id": self.zone_id,
            "structure_alignment": self.structure_alignment.value,
            "trend_alignment": self.trend_alignment.value,
            "liquidity_relation": self.liquidity_relation.value,
            "distance_to_price": round(self.distance_to_price, 6),
            "distance_atr": round(self.distance_atr, 4),
            "price_inside_zone": self.price_inside_zone,
            "freshness_bars": self.freshness_bars,
            "mitigation_state": self.mitigation_state,
            "timeframe": self.timeframe,
            "reference_price": self.reference_price,
            "liquidity_pool_id": self.liquidity_pool_id,
            "liquidity_sweep_id": self.liquidity_sweep_id,
            "htf_trend": self.htf_trend,
            "htf_trend_tf": self.htf_trend_tf,
            "trend_source": self.trend_source,
            "reasons": list(self.reasons),
            "ranking_version": self.ranking_version,
        }


def build_zone_context(
    zone: Any,
    *,
    price: float,
    atr: float = 0.0,
    structure: StructureSnapshot | None = None,
    liquidity: LiquiditySnapshot | None = None,
    trend: TrendDirection | None = None,
    htf_trend_tf: str | None = None,
    as_of_index: int | None = None,
) -> ZoneRankContext:
    """Build causal context for ``zone`` using only as-of facts.

    ``trend`` should be the canonical resolved HTF trend when available.
    If ``trend`` is None, ``trend_alignment`` falls back to structure
    ``external_bias`` (documented LTF fallback).
    """
    lo, hi = _zone_bounds(zone)
    mid = (lo + hi) / 2.0
    dist, inside = _distance_to_zone(price, lo, hi)
    atr_v = max(0.0, float(atr))
    dist_atr = (dist / atr_v) if atr_v > 0 else dist

    structure_bias = structure.external_bias if structure is not None else None
    structure_alignment = _align(zone.direction, structure_bias)
    if trend is not None:
        trend_bias = trend
        trend_source = f"resolved_htf:{htf_trend_tf}" if htf_trend_tf else "resolved_htf"
    else:
        trend_bias = structure_bias
        trend_source = "structure_external_bias_fallback"
    trend_alignment = _align(zone.direction, trend_bias)

    liq_rel, pool_id, sweep_id = _liquidity_relation(
        direction=zone.direction,
        lo=lo,
        hi=hi,
        mid=mid,
        liquidity=liquidity,
        atr=atr_v,
    )

    if as_of_index is not None:
        freshness = max(0, int(as_of_index) - int(zone.created_index))
    else:
        freshness = int(getattr(zone, "age_bars", 0) or 0)

    mitigation_state = zone.status.value if hasattr(zone.status, "value") else str(zone.status)
    timeframe = str(getattr(zone, "timeframe", "") or "")

    reasons: list[str] = [
        mitigation_state,
        f"structure_{structure_alignment.value.lower()}",
        f"trend_{trend_alignment.value.lower()}",
        f"trend_source={trend_source}",
        f"liquidity_{liq_rel.value.lower()}",
    ]
    if inside:
        reasons.append("price_inside_zone")
    else:
        reasons.append(f"distance={dist:.5f}")
    reasons.append(f"freshness_bars={freshness}")

    return ZoneRankContext(
        zone_id=zone.zone_id,
        structure_alignment=structure_alignment,
        trend_alignment=trend_alignment,
        liquidity_relation=liq_rel,
        distance_to_price=dist,
        distance_atr=dist_atr,
        price_inside_zone=inside,
        freshness_bars=freshness,
        mitigation_state=mitigation_state,
        timeframe=timeframe,
        reference_price=float(price),
        liquidity_pool_id=pool_id,
        liquidity_sweep_id=sweep_id,
        htf_trend=trend_bias.value if trend_bias is not None else None,
        htf_trend_tf=htf_trend_tf,
        trend_source=trend_source,
        reasons=tuple(reasons),
    )


# Lexicographic preference ranks (lower = better).
_STRUCTURE_RANK = {
    Alignment.ALIGNED: 0,
    Alignment.NEUTRAL: 1,
    Alignment.UNDEFINED: 2,
    Alignment.OPPOSED: 3,
}
_LIQUIDITY_RANK = {
    LiquidityRelation.ASSOCIATED_SWEEP: 0,
    LiquidityRelation.NEAR_RELEVANT: 1,
    LiquidityRelation.NONE: 2,
    LiquidityRelation.OPPOSING: 3,
}
_TREND_RANK = _STRUCTURE_RANK


def lifecycle_rank(status: Any) -> int:
    name = status.value if hasattr(status, "value") else str(status)
    order = {
        "ACTIVE": 0,
        "PARTIALLY_FILLED": 1,
        "TOUCHED": 1,
        "MITIGATED": 2,
        "INVALIDATED": 3,
        "EXPIRED": 4,
    }
    return order.get(name, 9)


def ranking_key(zone: Any, ctx: ZoneRankContext) -> tuple:
    """Deterministic sort key — lower sorts first."""
    return (
        lifecycle_rank(zone.status),
        _STRUCTURE_RANK[ctx.structure_alignment],
        _LIQUIDITY_RANK[ctx.liquidity_relation],
        _TREND_RANK[ctx.trend_alignment],
        ctx.distance_atr if ctx.distance_atr == ctx.distance_atr else ctx.distance_to_price,
        ctx.freshness_bars,
        ctx.zone_id,
    )

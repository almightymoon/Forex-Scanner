"""Adapt ranked Order Block zones to SMCPattern for DecisionEngine."""

from __future__ import annotations

from shared.types.models import SMCPattern, TrendDirection

from services.quant_engine.liquidity.models import LiquiditySnapshot
from services.quant_engine.market_structure.models import StructureSnapshot
from services.quant_engine.order_blocks.models import OBStatus, OrderBlockZone, OrderBlockZoneSet
from services.quant_engine.zones.ranking import DEFAULT_PATTERN_LIMIT, enrich_and_rank_zones


def rank_ob_zones(
    zones: tuple[OrderBlockZone, ...] | OrderBlockZoneSet,
    *,
    price: float,
    atr: float = 0.0,
    structure: StructureSnapshot | None = None,
    liquidity: LiquiditySnapshot | None = None,
    trend: TrendDirection | None = None,
    htf_trend_tf: str | None = None,
    as_of_index: int | None = None,
) -> list[OrderBlockZone]:
    zs = zones.zones if isinstance(zones, OrderBlockZoneSet) else zones
    ranked = enrich_and_rank_zones(
        zs,
        price=price,
        atr=atr,
        structure=structure,
        liquidity=liquidity,
        trend=trend,
        htf_trend_tf=htf_trend_tf,
        as_of_index=as_of_index if as_of_index is not None else (
            zones.as_of_index if isinstance(zones, OrderBlockZoneSet) else None
        ),
    )
    return [z for z, _ in ranked]


def patterns_from_ob_zones(
    zone_set: OrderBlockZoneSet | None,
    *,
    price: float | None = None,
    atr: float = 0.0,
    structure: StructureSnapshot | None = None,
    liquidity: LiquiditySnapshot | None = None,
    trend: TrendDirection | None = None,
    htf_trend_tf: str | None = None,
    limit: int = DEFAULT_PATTERN_LIMIT,
) -> list[SMCPattern]:
    if zone_set is None or not zone_set.zones:
        return []
    px = price if price is not None else (
        (zone_set.zones[-1].price_low + zone_set.zones[-1].price_high) / 2
    )
    ranked = enrich_and_rank_zones(
        zone_set.zones,
        price=px,
        atr=atr,
        structure=structure,
        liquidity=liquidity,
        trend=trend,
        htf_trend_tf=htf_trend_tf,
        as_of_index=zone_set.as_of_index,
    )
    out: list[SMCPattern] = []
    for rank_i, (z, ctx) in enumerate(ranked[:limit], start=1):
        strength = 75
        if z.status is OBStatus.TOUCHED:
            strength = 70
        elif z.status is OBStatus.MITIGATED:
            strength = 35
        out.append(
            SMCPattern(
                pattern_type="order_block",
                direction=z.direction,
                price_low=z.price_low,
                price_high=z.price_high,
                strength=strength,
                metadata={
                    "zone_id": z.zone_id,
                    "index": z.source_candle_index,
                    "created_index": z.created_index,
                    "impulse_ratio": z.impulse_ratio,
                    "status": z.status.value,
                    "mitigation_index": z.mitigation_index,
                    "source": "ob_lifecycle",
                    "age_bars": z.age_bars,
                    "rank": rank_i,
                    "zone_context": ctx.to_dict(),
                    "rank_reasons": list(ctx.reasons),
                },
            )
        )
    return out

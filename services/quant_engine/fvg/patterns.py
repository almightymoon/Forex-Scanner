"""Adapt ranked FVG zones to SMCPattern for DecisionEngine scoring.

Detector returns the full zone set. Ranking + soft-cap select patterns for DE —
they do not delete zones from the canonical set.
"""

from __future__ import annotations

from shared.types.models import SMCPattern, TrendDirection

from services.quant_engine.fvg.models import FVGStatus, FVGZone, FVGZoneSet
from services.quant_engine.liquidity.models import LiquiditySnapshot
from services.quant_engine.market_structure.models import StructureSnapshot
from services.quant_engine.zones.ranking import DEFAULT_PATTERN_LIMIT, enrich_and_rank_zones


def rank_fvg_zones(
    zones: tuple[FVGZone, ...] | FVGZoneSet,
    *,
    price: float,
    atr: float = 0.0,
    structure: StructureSnapshot | None = None,
    liquidity: LiquiditySnapshot | None = None,
    trend: TrendDirection | None = None,
    htf_trend_tf: str | None = None,
    as_of_index: int | None = None,
) -> list[FVGZone]:
    zs = zones.zones if isinstance(zones, FVGZoneSet) else zones
    ranked = enrich_and_rank_zones(
        zs,
        price=price,
        atr=atr,
        structure=structure,
        liquidity=liquidity,
        trend=trend,
        htf_trend_tf=htf_trend_tf,
        as_of_index=as_of_index if as_of_index is not None else (
            zones.as_of_index if isinstance(zones, FVGZoneSet) else None
        ),
    )
    return [z for z, _ in ranked]


def patterns_from_fvg_zones(
    zone_set: FVGZoneSet | None,
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
        (zone_set.zones[-1].lower_bound + zone_set.zones[-1].upper_bound) / 2
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
        strength = 65
        if z.status is FVGStatus.ACTIVE:
            strength = 75
        elif z.status is FVGStatus.PARTIALLY_FILLED:
            strength = 70
        elif z.status is FVGStatus.MITIGATED:
            strength = 40
        out.append(
            SMCPattern(
                pattern_type="fvg",
                direction=z.direction,
                price_low=z.lower_bound,
                price_high=z.upper_bound,
                strength=strength,
                metadata={
                    "zone_id": z.zone_id,
                    "gap_size": z.gap_size,
                    "status": z.status.value,
                    "fill_ratio": z.fill_ratio,
                    "created_index": z.created_index,
                    "mitigation_index": z.mitigation_index,
                    "source": "fvg_lifecycle",
                    "age_bars": z.age_bars,
                    "rank": rank_i,
                    "zone_context": ctx.to_dict(),
                    "rank_reasons": list(ctx.reasons),
                },
            )
        )
    return out

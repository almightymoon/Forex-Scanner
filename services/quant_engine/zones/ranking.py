"""Deterministic FVG/OB zone ranking with explainable context.

Soft-cap applies only after enrichment + ranking. ZoneSets stay complete.
"""

from __future__ import annotations

from typing import Any, Sequence

from shared.types.models import TrendDirection

from services.quant_engine.liquidity.models import LiquiditySnapshot
from services.quant_engine.market_structure.models import StructureSnapshot
from services.quant_engine.zones.context import (
    ZONE_RANKING_VERSION,
    ZoneRankContext,
    build_zone_context,
    ranking_key,
)

DEFAULT_PATTERN_LIMIT = 8


def enrich_and_rank_zones(
    zones: Sequence[Any],
    *,
    price: float,
    atr: float = 0.0,
    structure: StructureSnapshot | None = None,
    liquidity: LiquiditySnapshot | None = None,
    trend: TrendDirection | None = None,
    htf_trend_tf: str | None = None,
    as_of_index: int | None = None,
) -> list[tuple[Any, ZoneRankContext]]:
    """Return zones sorted by lexicographic context key (best first)."""
    enriched: list[tuple[Any, ZoneRankContext]] = []
    for z in zones:
        ctx = build_zone_context(
            z,
            price=price,
            atr=atr,
            structure=structure,
            liquidity=liquidity,
            trend=trend,
            htf_trend_tf=htf_trend_tf,
            as_of_index=as_of_index,
        )
        enriched.append((z, ctx))
    enriched.sort(key=lambda pair: ranking_key(pair[0], pair[1]))
    return enriched


__all__ = [
    "DEFAULT_PATTERN_LIMIT",
    "ZONE_RANKING_VERSION",
    "enrich_and_rank_zones",
]

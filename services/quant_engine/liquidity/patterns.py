"""Adapt LiquiditySnapshot → SMCPattern atoms for DecisionEngine scoring.

Liquidity Engine v1 is the single detector. SMC / DE consume these patterns;
they must not re-detect equal highs/lows or sweeps independently.
"""

from __future__ import annotations

from shared.types.models import SMCPattern, SignalDirection

from services.quant_engine.liquidity.models import (
    LiquiditySnapshot,
    PoolType,
    SweepKind,
)


def patterns_from_liquidity_snapshot(
    snapshot: LiquiditySnapshot | None,
) -> list[SMCPattern]:
    """Emit equal_highs / equal_lows / liquidity_sweep patterns from a snapshot."""
    if snapshot is None:
        return []

    patterns: list[SMCPattern] = []
    seen_eq: set[tuple[str, float]] = set()

    for pool in snapshot.active_pools:
        if pool.pool_type is PoolType.EQUAL_HIGH:
            key = ("equal_highs", round(pool.price, 5))
            if key in seen_eq:
                continue
            seen_eq.add(key)
            patterns.append(
                SMCPattern(
                    pattern_type="equal_highs",
                    direction=SignalDirection.SELL,
                    price_high=pool.price,
                    strength=int(60 + pool.strength_score * 30),
                    metadata={
                        "pool_id": pool.pool_id,
                        "pool_type": pool.pool_type.value,
                        "source": "liquidity_engine",
                        "source_timeframe": pool.source_timeframe,
                    },
                )
            )
        elif pool.pool_type is PoolType.EQUAL_LOW:
            key = ("equal_lows", round(pool.price, 5))
            if key in seen_eq:
                continue
            seen_eq.add(key)
            patterns.append(
                SMCPattern(
                    pattern_type="equal_lows",
                    direction=SignalDirection.BUY,
                    price_low=pool.price,
                    strength=int(60 + pool.strength_score * 30),
                    metadata={
                        "pool_id": pool.pool_id,
                        "pool_type": pool.pool_type.value,
                        "source": "liquidity_engine",
                        "source_timeframe": pool.source_timeframe,
                    },
                )
            )

    for sweep in snapshot.recent_sweeps:
        if sweep.kind is SweepKind.SWEEP_LOW:
            patterns.append(
                SMCPattern(
                    pattern_type="liquidity_sweep",
                    direction=SignalDirection.BUY,
                    price_low=sweep.level_price,
                    strength=int(70 + (10 if sweep.grade.value == "STRONG" else 0)),
                    metadata={
                        "swept_level": sweep.level_price,
                        "sweep_id": sweep.sweep_id,
                        "grade": sweep.grade.value,
                        "source": "liquidity_engine",
                    },
                )
            )
        elif sweep.kind is SweepKind.SWEEP_HIGH:
            patterns.append(
                SMCPattern(
                    pattern_type="liquidity_sweep",
                    direction=SignalDirection.SELL,
                    price_high=sweep.level_price,
                    strength=int(70 + (10 if sweep.grade.value == "STRONG" else 0)),
                    metadata={
                        "swept_level": sweep.level_price,
                        "sweep_id": sweep.sweep_id,
                        "grade": sweep.grade.value,
                        "source": "liquidity_engine",
                    },
                )
            )

    return patterns

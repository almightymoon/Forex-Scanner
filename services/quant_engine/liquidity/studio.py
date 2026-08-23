"""Studio overlay helpers for typed liquidity maps / snapshots."""

from __future__ import annotations

from typing import Any

from services.quant_engine.liquidity.models import (
    LiquidityMap,
    LiquiditySnapshot,
    PoolStatus,
    SweepKind,
    SweepQuality,
)


def liquidity_overlay_payload(
    liquidity_map: LiquidityMap | LiquiditySnapshot | None,
) -> dict[str, Any]:
    """Lightweight-charts friendly liquidity markers / level summaries."""

    if isinstance(liquidity_map, LiquiditySnapshot):
        levels: list[dict[str, Any]] = []
        for pool in liquidity_map.pools:
            if pool.price <= 0:
                continue
            color = "#38bdf8" if pool.side.value == "buy_side" else "#fb7185"
            if pool.status is not PoolStatus.ACTIVE:
                color = "#64748b"
            levels.append(
                {
                    "price": pool.price,
                    "kind": pool.pool_type.value,
                    "side": pool.side.value,
                    "source": pool.source_reference,
                    "source_timeframe": pool.source_timeframe,
                    "status": pool.status.value,
                    "color": color,
                    "label": pool.pool_type.value,
                }
            )
        sweeps: list[dict[str, Any]] = []
        for sweep in liquidity_map.sweeps:
            if sweep.kind is SweepKind.BREAKOUT:
                color = "#a78bfa"
            elif sweep.bias_quality is SweepQuality.CONTINUATION:
                color = "#22c55e"
            elif sweep.bias_quality is SweepQuality.STOP_HUNT:
                color = "#ef4444"
            else:
                color = "#94a3b8"
            sweeps.append(
                {
                    "direction": (
                        "SELL" if sweep.kind is SweepKind.SWEEP_HIGH else "BUY"
                    ),
                    "quality": sweep.grade.value,
                    "kind": sweep.kind.value,
                    "level_price": sweep.level_price,
                    "color": color,
                    "label": f"{sweep.kind.value}:{sweep.grade.value}",
                }
            )
        return {
            "liquidity_levels": levels,
            "liquidity_sweeps": sweeps,
            "session_tags": list(liquidity_map.session_tags),
            "kinds": sorted({p.pool_type.value for p in liquidity_map.pools}),
            "algorithm_version": liquidity_map.algorithm_version,
        }

    if liquidity_map is None:
        return {
            "liquidity_levels": [],
            "liquidity_sweeps": [],
            "session_tags": [],
            "kinds": [],
        }

    levels = []
    for level in liquidity_map.levels:
        if level.price <= 0:
            continue
        color = "#38bdf8" if level.side.value == "buy_side" else "#fb7185"
        levels.append(
            {
                "price": level.price,
                "kind": level.kind.value,
                "side": level.side.value,
                "source": level.source,
                "color": color,
                "label": level.kind.value,
            }
        )

    sweeps = []
    for sweep in liquidity_map.sweeps:
        color = (
            "#22c55e"
            if sweep.quality is SweepQuality.CONTINUATION
            else "#ef4444"
            if sweep.quality is SweepQuality.STOP_HUNT
            else "#94a3b8"
        )
        sweeps.append(
            {
                "direction": sweep.direction.value,
                "quality": sweep.quality.value,
                "level_price": sweep.level_price,
                "color": color,
                "label": f"SWP:{sweep.quality.value}",
            }
        )

    return {
        "liquidity_levels": levels,
        "liquidity_sweeps": sweeps,
        "session_tags": list(liquidity_map.session_tags),
        "kinds": sorted({level.kind.value for level in liquidity_map.levels}),
    }

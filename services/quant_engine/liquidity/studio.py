"""Studio overlay helpers for typed liquidity maps."""

from __future__ import annotations

from typing import Any

from services.quant_engine.liquidity.models import LiquidityMap, SweepQuality


def liquidity_overlay_payload(liquidity_map: LiquidityMap) -> dict[str, Any]:
    """Lightweight-charts friendly liquidity markers / level summaries."""

    levels: list[dict[str, Any]] = []
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

    sweeps: list[dict[str, Any]] = []
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

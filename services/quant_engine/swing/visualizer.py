"""Chart overlay data for swing visualization — no UI."""

from __future__ import annotations

from services.quant_engine.swing.models import ChartOverlay, Swing, SwingSide, SwingTier


def build_chart_overlay(swings: list[Swing], *, include_unconfirmed: bool = False) -> ChartOverlay:
    """Return marker/line coordinates suitable for chart libraries."""
    visible = swings if include_unconfirmed else [s for s in swings if s.confirmed]

    markers: list[dict] = []
    lines: list[dict] = []

    for swing in visible:
        color = _tier_color(swing)
        markers.append(
            {
                "id": swing.id,
                "x": swing.timestamp.isoformat(),
                "y": swing.price,
                "index": swing.index,
                "type": swing.type,
                "tier": swing.tier.value,
                "scope": swing.scope.value,
                "side": swing.side.value,
                "confirmed": swing.confirmed,
                "strength": swing.strength,
                "label": _marker_label(swing),
                "shape": "triangleDown" if swing.side == SwingSide.HIGH else "triangleUp",
                "color": color,
                "size": 12 if swing.tier == SwingTier.MAJOR else 8,
            }
        )

    for i in range(1, len(visible)):
        a, b = visible[i - 1], visible[i]
        lines.append(
            {
                "x0": a.timestamp.isoformat(),
                "y0": a.price,
                "x1": b.timestamp.isoformat(),
                "y1": b.price,
                "dash": "solid" if a.confirmed and b.confirmed else "dot",
                "color": "#64748b",
                "width": 1,
            }
        )

    zones: list[dict] = []
    highs = [s for s in visible if s.side == SwingSide.HIGH and s.tier == SwingTier.MAJOR]
    lows = [s for s in visible if s.side == SwingSide.LOW and s.tier == SwingTier.MAJOR]
    if highs and lows:
        last_high = highs[-1]
        last_low = lows[-1]
        zones.append(
            {
                "type": "range",
                "top": last_high.price,
                "bottom": last_low.price,
                "x0": min(last_high.timestamp, last_low.timestamp).isoformat(),
                "x1": max(last_high.timestamp, last_low.timestamp).isoformat(),
                "label": "major_range",
                "opacity": 0.08,
            }
        )

    return ChartOverlay(markers=markers, lines=lines, zones=zones)


def _tier_color(swing: Swing) -> str:
    if swing.tier == SwingTier.MAJOR:
        return "#22c55e" if swing.side == SwingSide.LOW else "#ef4444"
    return "#86efac" if swing.side == SwingSide.LOW else "#fca5a5"


def _marker_label(swing: Swing) -> str:
    parts = [swing.tier.value.upper()]
    if swing.scope.value != "neutral":
        parts.append(swing.scope.value.upper())
    parts.append(swing.side.value.upper())
    return " ".join(parts)

"""Swing visualization data for debugging and algorithm validation."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from shared.types.models import Candle

from swing_engine.models import DetectedSwing, SwingDirection, SwingScope, SwingTier


class SwingVisualizer:
    """Generate chart overlay data — no UI, plotting coordinates only."""

    def build(
        self,
        bars: list[Candle],
        swings: list[DetectedSwing],
        *,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
        include_unconfirmed: bool = False,
    ) -> dict[str, Any]:
        """Build visualization payload with optional time window zoom."""
        visible_bars = self._filter_bars(bars, window_start, window_end)
        visible_swings = self._filter_swings(
            swings, window_start, window_end, include_unconfirmed
        )

        return {
            "candlesticks": [
                {
                    "x": c.timestamp.isoformat(),
                    "open": c.open,
                    "high": c.high,
                    "low": c.low,
                    "close": c.close,
                    "volume": c.volume,
                    "index": i,
                }
                for i, c in enumerate(visible_bars)
            ],
            "swings": [self._swing_marker(s) for s in visible_swings],
            "lines": self._zigzag_lines(visible_swings),
            "confirmation_markers": self._confirmation_markers(visible_swings),
            "window": {
                "start": window_start.isoformat() if window_start else None,
                "end": window_end.isoformat() if window_end else None,
            },
            "legend": {
                "major_high": "#ef4444",
                "major_low": "#22c55e",
                "minor_high": "#fca5a5",
                "minor_low": "#86efac",
                "unconfirmed": "#94a3b8",
            },
        }

    def _filter_bars(
        self,
        bars: list[Candle],
        start: datetime | None,
        end: datetime | None,
    ) -> list[Candle]:
        if not start and not end:
            return bars
        out = []
        for c in bars:
            if start and c.timestamp < start:
                continue
            if end and c.timestamp > end:
                continue
            out.append(c)
        return out

    def _filter_swings(
        self,
        swings: list[DetectedSwing],
        start: datetime | None,
        end: datetime | None,
        include_unconfirmed: bool,
    ) -> list[DetectedSwing]:
        out = []
        for s in swings:
            if not include_unconfirmed and not s.confirmed:
                continue
            if start and s.timestamp < start:
                continue
            if end and s.timestamp > end:
                continue
            out.append(s)
        return out

    def _swing_marker(self, swing: DetectedSwing) -> dict[str, Any]:
        color = self._color(swing)
        return {
            "x": swing.timestamp.isoformat(),
            "y": swing.price,
            "pivot_index": swing.pivot_index,
            "direction": swing.direction.value,
            "tier": swing.tier.value,
            "scope": swing.scope.value,
            "strength": swing.strength,
            "confidence": swing.confidence,
            "confirmed": swing.confirmed,
            "label": f"{swing.tier.value} {swing.scope.value} {swing.direction.value}",
            "shape": "triangleDown" if swing.direction == SwingDirection.HIGH else "triangleUp",
            "color": color,
            "metadata": swing.metadata,
        }

    def _confirmation_markers(self, swings: list[DetectedSwing]) -> list[dict[str, Any]]:
        markers = []
        for s in swings:
            if not s.confirmed or not s.confirmed_timestamp:
                continue
            markers.append({
                "x": s.confirmed_timestamp.isoformat(),
                "y": s.price,
                "pivot_index": s.pivot_index,
                "confirmation_index": s.confirmation_index,
                "delay_bars": s.confirmation_delay,
                "label": f"CONF +{s.confirmation_delay}",
                "color": "#3b82f6",
            })
        return markers

    def _zigzag_lines(self, swings: list[DetectedSwing]) -> list[dict[str, Any]]:
        lines = []
        for i in range(1, len(swings)):
            a, b = swings[i - 1], swings[i]
            lines.append({
                "x0": a.timestamp.isoformat(),
                "y0": a.price,
                "x1": b.timestamp.isoformat(),
                "y1": b.price,
                "dash": "solid" if a.confirmed and b.confirmed else "dot",
                "color": "#64748b",
            })
        return lines

    def _color(self, swing: DetectedSwing) -> str:
        if not swing.confirmed:
            return "#94a3b8"
        if swing.tier == SwingTier.MAJOR:
            return "#ef4444" if swing.direction == SwingDirection.HIGH else "#22c55e"
        return "#fca5a5" if swing.direction == SwingDirection.HIGH else "#86efac"

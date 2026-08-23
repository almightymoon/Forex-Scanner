"""Proximity of SMC zones (OB/FVG) to recent structure events.

Used to soft-boost quality when a zone forms near a causal BOS/CHoCH break
without changing production scoring.yaml base weights.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from shared.types.models import SMCPattern, SignalDirection, TrendDirection

from services.quant_engine.market_structure.models import StructureEvent, StructureSnapshot


@dataclass(frozen=True)
class StructureProximity:
    bars_to_event: int | None
    price_distance: float | None
    event_id: str | None
    agrees_with_event: bool
    boost: int  # additive score points (0..2)
    label: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "bars_to_event": self.bars_to_event,
            "price_distance": self.price_distance,
            "event_id": self.event_id,
            "agrees_with_event": self.agrees_with_event,
            "boost": self.boost,
            "label": self.label,
        }


def _pattern_index(pattern: SMCPattern, candle_count: int) -> int:
    meta = pattern.metadata or {}
    for key in ("index", "break_index", "mid_index"):
        if key in meta and meta[key] is not None:
            try:
                return int(meta[key])
            except (TypeError, ValueError):
                continue
    return max(0, candle_count - 1)


def _pattern_price(pattern: SMCPattern) -> float | None:
    if pattern.price_high is not None and pattern.price_low is not None:
        return (float(pattern.price_high) + float(pattern.price_low)) / 2.0
    if pattern.price_high is not None:
        return float(pattern.price_high)
    if pattern.price_low is not None:
        return float(pattern.price_low)
    return None


def _event_agrees(pattern: SMCPattern, event: StructureEvent) -> bool:
    if pattern.direction is SignalDirection.BUY:
        return event.direction is TrendDirection.BULLISH
    if pattern.direction is SignalDirection.SELL:
        return event.direction is TrendDirection.BEARISH
    return False


def assess_structure_proximity(
    pattern: SMCPattern,
    snapshot: StructureSnapshot | None,
    *,
    candle_count: int,
    max_bars: int = 12,
    atr: float = 0.0,
) -> StructureProximity:
    """Score how close a zone is to the nearest agreeing structure event."""

    if snapshot is None or not snapshot.events:
        return StructureProximity(
            bars_to_event=None,
            price_distance=None,
            event_id=None,
            agrees_with_event=False,
            boost=0,
            label="No structure events for proximity",
        )

    idx = _pattern_index(pattern, candle_count)
    price = _pattern_price(pattern)
    best: StructureEvent | None = None
    best_bars = 10**9
    for event in snapshot.events:
        bars = abs(int(event.break_index) - idx)
        if bars > max_bars:
            continue
        if not _event_agrees(pattern, event):
            continue
        if bars < best_bars:
            best_bars = bars
            best = event

    if best is None:
        return StructureProximity(
            bars_to_event=None,
            price_distance=None,
            event_id=None,
            agrees_with_event=False,
            boost=0,
            label="No nearby agreeing structure event",
        )

    dist = None
    if price is not None:
        dist = abs(price - float(best.level_price))
    boost = 2 if best_bars <= 3 else 1 if best_bars <= max_bars else 0
    if atr > 0 and dist is not None and dist > atr * 2.5:
        boost = max(0, boost - 1)
        label = (
            f"Near {best.event_type.value} ({best_bars} bars) but price stretched"
        )
    else:
        label = f"Near {best.event_type.value} at bar {best.break_index} ({best_bars} bars)"

    return StructureProximity(
        bars_to_event=best_bars,
        price_distance=dist,
        event_id=best.event_id,
        agrees_with_event=True,
        boost=boost,
        label=label,
    )

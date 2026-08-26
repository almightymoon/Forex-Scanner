"""Fair Value Gap zone models — causal lifecycle representation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from shared.types.models import SignalDirection, Timeframe


class FVGStatus(str, Enum):
    ACTIVE = "ACTIVE"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    MITIGATED = "MITIGATED"


@dataclass(frozen=True)
class FVGZone:
    """One FVG imbalance with deterministic lifecycle fields."""

    zone_id: str
    symbol: str
    timeframe: str
    direction: SignalDirection  # BUY = bullish FVG, SELL = bearish
    lower_bound: float
    upper_bound: float
    created_index: int
    created_timestamp: datetime | None
    source_candle_indices: tuple[int, int, int]  # c1, c2, c3
    status: FVGStatus
    first_touch_index: int | None = None
    first_touch_timestamp: datetime | None = None
    mitigation_index: int | None = None
    mitigation_timestamp: datetime | None = None
    fill_ratio: float = 0.0
    age_bars: int = 0

    @property
    def gap_size(self) -> float:
        return max(0.0, self.upper_bound - self.lower_bound)

    def to_dict(self) -> dict[str, Any]:
        return {
            "zone_id": self.zone_id,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "direction": self.direction.value,
            "lower_bound": self.lower_bound,
            "upper_bound": self.upper_bound,
            "created_index": self.created_index,
            "created_timestamp": (
                self.created_timestamp.isoformat() if self.created_timestamp else None
            ),
            "source_candle_indices": list(self.source_candle_indices),
            "status": self.status.value,
            "first_touch_index": self.first_touch_index,
            "first_touch_timestamp": (
                self.first_touch_timestamp.isoformat()
                if self.first_touch_timestamp
                else None
            ),
            "mitigation_index": self.mitigation_index,
            "mitigation_timestamp": (
                self.mitigation_timestamp.isoformat()
                if self.mitigation_timestamp
                else None
            ),
            "fill_ratio": round(self.fill_ratio, 4),
            "gap_size": round(self.gap_size, 6),
            "age_bars": self.age_bars,
        }


@dataclass(frozen=True)
class FVGZoneSet:
    """Complete causal FVG set for one as-of index."""

    symbol: str
    timeframe: str
    as_of_index: int
    zones: tuple[FVGZone, ...]
    algorithm_version: str = "1.0.0"

    @property
    def active(self) -> tuple[FVGZone, ...]:
        return tuple(
            z
            for z in self.zones
            if z.status in (FVGStatus.ACTIVE, FVGStatus.PARTIALLY_FILLED)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "as_of_index": self.as_of_index,
            "algorithm_version": self.algorithm_version,
            "zone_count": len(self.zones),
            "active_count": len(self.active),
            "zones": [z.to_dict() for z in self.zones],
        }

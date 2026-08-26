"""Order Block zone models — causal lifecycle representation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from shared.types.models import SignalDirection


class OBStatus(str, Enum):
    ACTIVE = "ACTIVE"
    TOUCHED = "TOUCHED"
    MITIGATED = "MITIGATED"


@dataclass(frozen=True)
class OrderBlockZone:
    zone_id: str
    symbol: str
    timeframe: str
    direction: SignalDirection
    price_low: float
    price_high: float
    source_candle_index: int
    created_index: int  # confirmation candle index (source+1)
    created_timestamp: datetime | None
    impulse_ratio: float
    status: OBStatus
    first_touch_index: int | None = None
    first_touch_timestamp: datetime | None = None
    mitigation_index: int | None = None
    mitigation_timestamp: datetime | None = None
    age_bars: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "zone_id": self.zone_id,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "direction": self.direction.value,
            "price_low": self.price_low,
            "price_high": self.price_high,
            "source_candle_index": self.source_candle_index,
            "created_index": self.created_index,
            "created_timestamp": (
                self.created_timestamp.isoformat() if self.created_timestamp else None
            ),
            "impulse_ratio": round(self.impulse_ratio, 4),
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
            "age_bars": self.age_bars,
        }


@dataclass(frozen=True)
class OrderBlockZoneSet:
    symbol: str
    timeframe: str
    as_of_index: int
    zones: tuple[OrderBlockZone, ...]
    algorithm_version: str = "1.0.0"

    @property
    def active(self) -> tuple[OrderBlockZone, ...]:
        return tuple(
            z for z in self.zones if z.status in (OBStatus.ACTIVE, OBStatus.TOUCHED)
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

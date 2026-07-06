"""Swing detection domain models."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from shared.types.models import Timeframe, to_dict


class SwingSide(str, Enum):
    HIGH = "high"
    LOW = "low"


class SwingTier(str, Enum):
    MAJOR = "major"
    MINOR = "minor"


class SwingScope(str, Enum):
    INTERNAL = "internal"
    EXTERNAL = "external"
    NEUTRAL = "neutral"


@dataclass
class Swing:
    """Production swing point — immutable once confirmed."""

    symbol: str
    timeframe: Timeframe
    timestamp: datetime
    price: float
    index: int
    side: SwingSide
    confirmed: bool
    strength: float
    tier: SwingTier
    scope: SwingScope
    lookback: int
    lookforward: int
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def type(self) -> str:
        """Canonical type string, e.g. swing_high, swing_low."""
        return f"swing_{self.side.value}"

    @property
    def quality(self) -> str:
        """Human-readable quality label combining tier and scope."""
        if self.scope != SwingScope.NEUTRAL:
            return f"{self.tier.value}_{self.scope.value}"
        return self.tier.value

    @property
    def kind(self) -> str:
        """Backward-compatible alias used by legacy SwingPoint consumers."""
        return self.side.value

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "symbol": self.symbol,
            "timeframe": self.timeframe.value,
            "timestamp": self.timestamp.isoformat(),
            "price": self.price,
            "index": self.index,
            "type": self.type,
            "side": self.side.value,
            "tier": self.tier.value,
            "scope": self.scope.value,
            "quality": self.quality,
            "confirmed": self.confirmed,
            "strength": round(self.strength, 1),
            "lookback": self.lookback,
            "lookforward": self.lookforward,
            "metadata": to_dict(self.metadata),
        }


@dataclass
class SwingDetectionResult:
    """Full detector output with explainability."""

    swings: list[Swing]
    symbol: str
    timeframe: Timeframe
    candle_count: int
    confirmed_count: int
    major_count: int
    minor_count: int
    validation_passed: bool
    validation_issues: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def swing_highs(self) -> list[Swing]:
        return [s for s in self.swings if s.side == SwingSide.HIGH]

    @property
    def swing_lows(self) -> list[Swing]:
        return [s for s in self.swings if s.side == SwingSide.LOW]

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe.value,
            "candle_count": self.candle_count,
            "confirmed_count": self.confirmed_count,
            "major_count": self.major_count,
            "minor_count": self.minor_count,
            "validation_passed": self.validation_passed,
            "validation_issues": self.validation_issues,
            "swings": [s.to_dict() for s in self.swings],
            "metadata": to_dict(self.metadata),
        }


@dataclass
class ChartOverlay:
    """Plotting coordinates for chart overlays — no UI."""

    markers: list[dict[str, Any]]
    lines: list[dict[str, Any]]
    zones: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {"markers": self.markers, "lines": self.lines, "zones": self.zones}

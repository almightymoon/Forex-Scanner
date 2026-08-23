"""Typed liquidity levels and sweep assessments for structure-aware scoring."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from shared.types.models import SignalDirection, TrendDirection


class LiquiditySide(str, Enum):
    BUY_SIDE = "buy_side"  # equal lows / swept lows — buy-side liquidity
    SELL_SIDE = "sell_side"  # equal highs / swept highs — sell-side liquidity


class LiquidityKind(str, Enum):
    EQUAL_HIGHS = "equal_highs"
    EQUAL_LOWS = "equal_lows"
    SWING_HIGH = "swing_high"
    SWING_LOW = "swing_low"
    SESSION_ASIA_HIGH = "session_asia_high"
    SESSION_ASIA_LOW = "session_asia_low"
    SWEPT_LEVEL = "swept_level"


class SweepQuality(str, Enum):
    CONTINUATION = "continuation"  # sweep agrees with external bias
    STOP_HUNT = "stop_hunt"  # sweep against bias / likely trap
    NEUTRAL = "neutral"


@dataclass(frozen=True)
class LiquidityLevel:
    """A discrete liquidity pool or reference level."""

    kind: LiquidityKind
    side: LiquiditySide
    price: float
    strength: float = 0.0
    source: str = "smc"  # smc | structure | session
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "side": self.side.value,
            "price": self.price,
            "strength": round(self.strength, 3),
            "source": self.source,
            "metadata": dict(sorted((self.metadata or {}).items())),
        }


@dataclass(frozen=True)
class LiquiditySweepAssessment:
    """Sweep scored against external structure bias."""

    direction: SignalDirection
    quality: SweepQuality
    level_price: float | None
    agrees_with_bias: bool
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "direction": self.direction.value,
            "quality": self.quality.value,
            "level_price": self.level_price,
            "agrees_with_bias": self.agrees_with_bias,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class LiquidityMap:
    """Canonical liquidity view for one scan."""

    levels: tuple[LiquidityLevel, ...]
    sweeps: tuple[LiquiditySweepAssessment, ...]
    session_tags: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "levels": [level.to_dict() for level in self.levels],
            "sweeps": [sweep.to_dict() for sweep in self.sweeps],
            "session_tags": list(self.session_tags),
            "level_count": len(self.levels),
            "sweep_count": len(self.sweeps),
        }

    @property
    def pool_labels(self) -> list[str]:
        """Backward-compatible string pool labels."""
        labels: list[str] = []
        for level in self.levels:
            if level.kind is LiquidityKind.EQUAL_HIGHS and "equal_highs" not in labels:
                labels.append("equal_highs")
            elif level.kind is LiquidityKind.EQUAL_LOWS and "equal_lows" not in labels:
                labels.append("equal_lows")
        return labels

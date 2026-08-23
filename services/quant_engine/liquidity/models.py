"""Liquidity Engine v1 — typed pools, sweeps, and LiquiditySnapshot.

Backward-compatible types (LiquidityMap, SweepQuality CONTINUATION/STOP_HUNT)
remain for confluence / DecisionEngine scoring.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from shared.types.models import SignalDirection, TrendDirection, Timeframe

LIQUIDITY_ENGINE_VERSION = "1.0.0"


class LiquiditySide(str, Enum):
    BUY_SIDE = "buy_side"
    SELL_SIDE = "sell_side"


class LiquidityKind(str, Enum):
    """Legacy level kinds (LiquidityMap adapter)."""

    EQUAL_HIGHS = "equal_highs"
    EQUAL_LOWS = "equal_lows"
    SWING_HIGH = "swing_high"
    SWING_LOW = "swing_low"
    SESSION_ASIA_HIGH = "session_asia_high"
    SESSION_ASIA_LOW = "session_asia_low"
    SWEPT_LEVEL = "swept_level"


class PoolType(str, Enum):
    EQUAL_HIGH = "EQUAL_HIGH"
    EQUAL_LOW = "EQUAL_LOW"
    STRUCTURAL_HIGH = "STRUCTURAL_HIGH"
    STRUCTURAL_LOW = "STRUCTURAL_LOW"
    SESSION_HIGH = "SESSION_HIGH"
    SESSION_LOW = "SESSION_LOW"


class PoolStatus(str, Enum):
    ACTIVE = "ACTIVE"
    SWEPT = "SWEPT"
    INVALIDATED = "INVALIDATED"
    EXPIRED = "EXPIRED"


class PoolStrength(str, Enum):
    WEAK = "WEAK"
    MODERATE = "MODERATE"
    STRONG = "STRONG"


class SweepKind(str, Enum):
    SWEEP_HIGH = "SWEEP_HIGH"
    SWEEP_LOW = "SWEEP_LOW"
    BREAKOUT = "BREAKOUT"


class SweepGrade(str, Enum):
    """Penetration / rejection quality (distinct from bias SweepQuality)."""

    WEAK = "WEAK"
    MODERATE = "MODERATE"
    STRONG = "STRONG"


class SweepQuality(str, Enum):
    """Bias alignment relative to external structure."""

    CONTINUATION = "continuation"
    STOP_HUNT = "stop_hunt"
    NEUTRAL = "neutral"


@dataclass(frozen=True)
class LiquidityPool:
    """Typed liquidity pool with causal availability metadata."""

    pool_id: str
    pool_type: PoolType
    side: LiquiditySide
    price: float
    symbol: str
    source_timeframe: str
    scope: str  # EXTERNAL | INTERNAL | SESSION | CLUSTER
    status: PoolStatus
    strength: PoolStrength
    strength_score: float
    touches: int
    created_index: int
    available_index: int
    created_at: datetime | None
    available_at: datetime | None
    source_reference: str
    reasons: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pool_id": self.pool_id,
            "pool_type": self.pool_type.value,
            "side": self.side.value,
            "price": self.price,
            "symbol": self.symbol,
            "source_timeframe": self.source_timeframe,
            "scope": self.scope,
            "status": self.status.value,
            "strength": self.strength.value,
            "strength_score": round(self.strength_score, 3),
            "touches": self.touches,
            "created_index": self.created_index,
            "available_index": self.available_index,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "available_at": self.available_at.isoformat() if self.available_at else None,
            "source_reference": self.source_reference,
            "reasons": list(self.reasons),
            "metadata": dict(sorted(self.metadata.items())),
            "liquidity_engine_version": LIQUIDITY_ENGINE_VERSION,
        }


@dataclass(frozen=True)
class LiquiditySweepEvent:
    """Sweep or breakout against a known pool."""

    sweep_id: str
    kind: SweepKind
    pool_id: str
    pool_type: PoolType
    level_price: float
    bar_index: int
    timestamp: datetime | None
    penetration: float
    penetration_atr: float
    rejection_pct: float
    grade: SweepGrade
    bias_quality: SweepQuality
    reasons: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sweep_id": self.sweep_id,
            "kind": self.kind.value,
            "pool_id": self.pool_id,
            "pool_type": self.pool_type.value,
            "level_price": self.level_price,
            "bar_index": self.bar_index,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "penetration": round(self.penetration, 6),
            "penetration_atr": round(self.penetration_atr, 4),
            "rejection_pct": round(self.rejection_pct, 1),
            "grade": self.grade.value,
            "bias_quality": self.bias_quality.value,
            "reasons": list(self.reasons),
            "metadata": dict(sorted(self.metadata.items())),
            "liquidity_engine_version": LIQUIDITY_ENGINE_VERSION,
        }


@dataclass(frozen=True)
class LiquidityLevel:
    """Legacy discrete level for LiquidityMap compatibility."""

    kind: LiquidityKind
    side: LiquiditySide
    price: float
    strength: float = 0.0
    source: str = "smc"
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
    """Legacy bias-only sweep assessment for confluence."""

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
    """Legacy map retained for FeatureExtractor / confluence."""

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
        labels: list[str] = []
        for level in self.levels:
            if level.kind is LiquidityKind.EQUAL_HIGHS and "equal_highs" not in labels:
                labels.append("equal_highs")
            elif level.kind is LiquidityKind.EQUAL_LOWS and "equal_lows" not in labels:
                labels.append("equal_lows")
        return labels


@dataclass(frozen=True)
class LiquiditySnapshot:
    """Canonical Liquidity Engine v1 output."""

    symbol: str
    timeframe: str
    as_of_index: int
    pools: tuple[LiquidityPool, ...]
    sweeps: tuple[LiquiditySweepEvent, ...]
    session_tags: tuple[str, ...]
    atr: float
    equality_tolerance: float
    algorithm_version: str = LIQUIDITY_ENGINE_VERSION
    legacy_map: LiquidityMap | None = None

    @property
    def active_pools(self) -> tuple[LiquidityPool, ...]:
        return tuple(p for p in self.pools if p.status is PoolStatus.ACTIVE)

    @property
    def swept_pools(self) -> tuple[LiquidityPool, ...]:
        return tuple(p for p in self.pools if p.status is PoolStatus.SWEPT)

    @property
    def recent_sweeps(self) -> tuple[LiquiditySweepEvent, ...]:
        return tuple(s for s in self.sweeps if s.kind is not SweepKind.BREAKOUT)

    @property
    def high_liquidity_count(self) -> int:
        return sum(1 for p in self.active_pools if p.side is LiquiditySide.SELL_SIDE)

    @property
    def low_liquidity_count(self) -> int:
        return sum(1 for p in self.active_pools if p.side is LiquiditySide.BUY_SIDE)

    def nearest_high_liquidity(self, price: float) -> LiquidityPool | None:
        highs = [p for p in self.active_pools if p.side is LiquiditySide.SELL_SIDE and p.price >= price]
        return min(highs, key=lambda p: p.price - price) if highs else None

    def nearest_low_liquidity(self, price: float) -> LiquidityPool | None:
        lows = [p for p in self.active_pools if p.side is LiquiditySide.BUY_SIDE and p.price <= price]
        return max(lows, key=lambda p: p.price) if lows else None

    def to_dict(self) -> dict[str, Any]:
        last_price = None
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "as_of_index": self.as_of_index,
            "algorithm_version": self.algorithm_version,
            "atr": round(self.atr, 6),
            "equality_tolerance": round(self.equality_tolerance, 8),
            "active_pools": [p.to_dict() for p in self.active_pools],
            "swept_pools": [p.to_dict() for p in self.swept_pools],
            "recent_sweeps": [s.to_dict() for s in self.recent_sweeps],
            "breakouts": [
                s.to_dict() for s in self.sweeps if s.kind is SweepKind.BREAKOUT
            ],
            "high_liquidity_count": self.high_liquidity_count,
            "low_liquidity_count": self.low_liquidity_count,
            "session_tags": list(self.session_tags),
            "legacy_map": self.legacy_map.to_dict() if self.legacy_map else None,
        }

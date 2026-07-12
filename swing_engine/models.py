"""Detected swing domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from shared.types.models import Timeframe, to_dict


class SwingDirection(str, Enum):
    HIGH = "HIGH"
    LOW = "LOW"


class SwingTier(str, Enum):
    MAJOR = "MAJOR"
    MINOR = "MINOR"


class SwingScope(str, Enum):
    INTERNAL = "INTERNAL"
    EXTERNAL = "EXTERNAL"
    NEUTRAL = "NEUTRAL"


@dataclass
class DetectedSwing:
    """Production swing output for downstream market structure modules."""

    timestamp: datetime
    price: float
    direction: SwingDirection
    tier: SwingTier
    scope: SwingScope
    pivot_index: int
    confirmed: bool = False
    confirmed_timestamp: datetime | None = None
    confirmation_index: int | None = None
    confirmation_delay: int = 0
    strength: int = 1
    score: float = 0.0
    confidence: float = 0.0
    reasoning: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def type_label(self) -> str:
        return f"{self.tier.value}_{self.scope.value}_{self.direction.value}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "price": self.price,
            "direction": self.direction.value,
            "tier": self.tier.value,
            "scope": self.scope.value,
            "type": self.type_label,
            "pivot_index": self.pivot_index,
            "confirmed": self.confirmed,
            "confirmed_timestamp": self.confirmed_timestamp.isoformat() if self.confirmed_timestamp else None,
            "confirmation_index": self.confirmation_index,
            "confirmation_delay": self.confirmation_delay,
            "strength": self.strength,
            "score": round(self.score, 2),
            "confidence": round(self.confidence, 4),
            "reasoning": list(self.reasoning),
            "metadata": to_dict(self.metadata),
        }


@dataclass
class DetectionResult:
    """Engine output with audit trail."""

    swings: list[DetectedSwing]
    symbol: str
    timeframe: Timeframe
    bar_count: int
    stage_logs: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def confirmed_swings(self) -> list[DetectedSwing]:
        return [s for s in self.swings if s.confirmed]

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe.value,
            "bar_count": self.bar_count,
            "swing_count": len(self.swings),
            "confirmed_count": len(self.confirmed_swings),
            "swings": [s.to_dict() for s in self.swings],
            "stage_logs": self.stage_logs,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class BenchmarkLabel:
    pivot_index: int
    timestamp: datetime
    price: float
    direction: SwingDirection
    tier: SwingTier = SwingTier.MAJOR
    scope: SwingScope = SwingScope.EXTERNAL


@dataclass
class EvaluationReport:
    precision: float
    recall: float
    f1_score: float
    false_positives: int
    false_negatives: int
    true_positives: int
    average_detection_delay_bars: float
    average_price_error_pips: float
    average_time_error_bars: float
    major_precision: float = 0.0
    major_recall: float = 0.0
    external_precision: float = 0.0
    external_recall: float = 0.0
    matched_pairs: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1_score": round(self.f1_score, 4),
            "false_positives": self.false_positives,
            "false_negatives": self.false_negatives,
            "true_positives": self.true_positives,
            "average_detection_delay_bars": round(self.average_detection_delay_bars, 2),
            "average_price_error_pips": round(self.average_price_error_pips, 2),
            "average_time_error_bars": round(self.average_time_error_bars, 2),
            "major_precision": round(self.major_precision, 4),
            "major_recall": round(self.major_recall, 4),
            "external_precision": round(self.external_precision, 4),
            "external_recall": round(self.external_recall, 4),
            "matched_pairs": self.matched_pairs,
            "metadata": self.metadata,
        }

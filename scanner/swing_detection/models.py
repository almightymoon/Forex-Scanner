"""Domain models for the Swing Detection Engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from shared.types.models import Timeframe, to_dict


class SwingDirection(str, Enum):
    HIGH = "HIGH"
    LOW = "LOW"


class SwingClassification(str, Enum):
    MAJOR = "MAJOR"
    MINOR = "MINOR"


@dataclass(frozen=True)
class PivotCandidate:
    """Raw pivot before filtering and confirmation."""

    pivot_index: int
    pivot_timestamp: datetime
    price: float
    direction: SwingDirection


@dataclass
class Swing:
    """Confirmed or pending swing output."""

    timestamp: datetime
    price: float
    direction: SwingDirection
    pivot_index: int
    confirmed: bool = False
    confirmed_timestamp: datetime | None = None
    confirmation_index: int | None = None
    confirmation_delay: int = 0
    strength: int = 1
    score: float = 0.0
    classification: SwingClassification = SwingClassification.MINOR
    reasoning: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "price": self.price,
            "direction": self.direction.value,
            "pivot_index": self.pivot_index,
            "confirmed": self.confirmed,
            "confirmed_timestamp": self.confirmed_timestamp.isoformat() if self.confirmed_timestamp else None,
            "confirmation_index": self.confirmation_index,
            "confirmation_delay": self.confirmation_delay,
            "strength": self.strength,
            "score": round(self.score, 2),
            "classification": self.classification.value,
            "reasoning": list(self.reasoning),
            "metadata": to_dict(self.metadata),
        }


@dataclass
class PipelineStageLog:
    """Structured log entry for a pipeline stage."""

    stage: str
    input_count: int
    output_count: int
    rejected: int
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class SwingDetectionOutput:
    """Final engine output with audit trail."""

    swings: list[Swing]
    symbol: str
    timeframe: Timeframe
    candle_count: int
    stage_logs: list[PipelineStageLog] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def confirmed_swings(self) -> list[Swing]:
        return [s for s in self.swings if s.confirmed]

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe.value,
            "candle_count": self.candle_count,
            "swing_count": len(self.swings),
            "confirmed_count": len(self.confirmed_swings),
            "swings": [s.to_dict() for s in self.swings],
            "stage_logs": [
                {
                    "stage": log.stage,
                    "input_count": log.input_count,
                    "output_count": log.output_count,
                    "rejected": log.rejected,
                    "details": log.details,
                }
                for log in self.stage_logs
            ],
            "metadata": to_dict(self.metadata),
        }


@dataclass(frozen=True)
class BenchmarkSwing:
    """Ground-truth swing label for evaluation."""

    pivot_index: int
    timestamp: datetime
    price: float
    direction: SwingDirection


@dataclass
class EvaluationReport:
    """Structured evaluation metrics."""

    precision: float
    recall: float
    f1_score: float
    average_detection_delay_bars: float
    average_price_error_pips: float
    false_positives: int
    false_negatives: int
    true_positives: int
    matched_pairs: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1_score": round(self.f1_score, 4),
            "average_detection_delay_bars": round(self.average_detection_delay_bars, 2),
            "average_price_error_pips": round(self.average_price_error_pips, 2),
            "false_positives": self.false_positives,
            "false_negatives": self.false_negatives,
            "true_positives": self.true_positives,
            "matched_pairs": self.matched_pairs,
            "metadata": self.metadata,
        }

"""Domain models for swing_engine."""

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


# Legacy aliases
SwingClassification = SwingTier


@dataclass(frozen=True)
class PivotCandidate:
    pivot_index: int
    pivot_timestamp: datetime
    price: float
    direction: SwingDirection
    strength: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pivot_index": self.pivot_index,
            "timestamp": self.pivot_timestamp.isoformat(),
            "price": self.price,
            "direction": self.direction.value,
            "strength": round(self.strength, 2),
            "metadata": to_dict(self.metadata),
        }


@dataclass(frozen=True)
class RejectedCandidate:
    """Pivot rejected at a pipeline stage with reason."""

    candidate: PivotCandidate
    stage: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"stage": self.stage, "reason": self.reason, **self.candidate.to_dict()}


@dataclass
class InternalSwing:
    """Intermediate swing after confirmation, before final scoring."""

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
    normalized_score: float = 0.0
    tier: SwingTier = SwingTier.MINOR
    reasoning: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DetectedSwing:
    """Final production swing output."""

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
    normalized_score: float = 0.0
    confidence: float = 0.0
    reasoning: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def type_label(self) -> str:
        return f"{self.tier.value}_{self.scope.value}_{self.direction.value}"

    @property
    def classification(self) -> SwingTier:
        """Legacy alias for tier."""
        return self.tier

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
            "normalized_score": round(self.normalized_score, 2),
            "confidence": round(self.confidence, 4),
            "reasoning": list(self.reasoning),
            "metadata": to_dict(self.metadata),
        }


@dataclass
class PipelineArtifacts:
    """Intermediate pipeline results for debugging."""

    pivot_candidates: list[PivotCandidate] = field(default_factory=list)
    noise_filtered: list[PivotCandidate] = field(default_factory=list)
    noise_rejected: list[RejectedCandidate] = field(default_factory=list)
    atr_validated: list[PivotCandidate] = field(default_factory=list)
    atr_rejected: list[RejectedCandidate] = field(default_factory=list)
    leg_validated: list[PivotCandidate] = field(default_factory=list)
    leg_rejected: list[RejectedCandidate] = field(default_factory=list)
    confirmed_swings: list[InternalSwing] = field(default_factory=list)
    unconfirmed_swings: list[InternalSwing] = field(default_factory=list)
    decision_timeline: list[dict[str, Any]] = field(default_factory=list)
    atr_series: list[float] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pivot_candidates": [p.to_dict() for p in self.pivot_candidates],
            "noise_filtered": [p.to_dict() for p in self.noise_filtered],
            "noise_rejected": [r.to_dict() for r in self.noise_rejected],
            "atr_validated": [p.to_dict() for p in self.atr_validated],
            "atr_rejected": [r.to_dict() for r in self.atr_rejected],
            "leg_validated": [p.to_dict() for p in self.leg_validated],
            "leg_rejected": [r.to_dict() for r in self.leg_rejected],
            "confirmed_swings": len(self.confirmed_swings),
            "unconfirmed_swings": len(self.unconfirmed_swings),
        }


@dataclass
class PerformanceMetrics:
    """Runtime and throughput metrics."""

    symbol: str
    timeframe: str
    version: str
    runtime_ms: float
    bar_count: int
    swing_count: int
    bars_per_second: float
    swings_per_second: float
    peak_memory_mb: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "version": self.version,
            "runtime_ms": round(self.runtime_ms, 2),
            "bar_count": self.bar_count,
            "swing_count": self.swing_count,
            "bars_per_second": round(self.bars_per_second, 1),
            "swings_per_second": round(self.swings_per_second, 2),
            "peak_memory_mb": round(self.peak_memory_mb, 2),
        }


@dataclass
class DetectionResult:
    swings: list[DetectedSwing]
    symbol: str
    timeframe: Timeframe
    bar_count: int
    version: str = "1.0.0"
    artifacts: PipelineArtifacts = field(default_factory=PipelineArtifacts)
    performance: PerformanceMetrics | None = None
    stage_logs: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def confirmed_swings(self) -> list[DetectedSwing]:
        return [s for s in self.swings if s.confirmed]

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe.value,
            "version": self.version,
            "bar_count": self.bar_count,
            "swing_count": len(self.swings),
            "confirmed_count": len(self.confirmed_swings),
            "swings": [s.to_dict() for s in self.swings],
            "artifacts": self.artifacts.to_dict(),
            "performance": self.performance.to_dict() if self.performance else None,
            "stage_logs": self.stage_logs,
            "metadata": to_dict(self.metadata),
        }


@dataclass(frozen=True)
class BenchmarkLabel:
    pivot_index: int
    timestamp: datetime
    price: float
    direction: SwingDirection
    tier: SwingTier = SwingTier.MAJOR
    scope: SwingScope = SwingScope.EXTERNAL


BenchmarkSwing = BenchmarkLabel


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
    average_confidence: float = 0.0
    average_strength: float = 0.0
    repainting_rate: float = 0.0
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
            "average_confidence": round(self.average_confidence, 4),
            "average_strength": round(self.average_strength, 2),
            "repainting_rate": round(self.repainting_rate, 4),
            "matched_pairs": self.matched_pairs,
            "metadata": self.metadata,
        }


# Legacy pipeline types
PipelineStageLog = dict
SwingDetectionOutput = DetectionResult
Swing = InternalSwing
SwingSide = SwingDirection

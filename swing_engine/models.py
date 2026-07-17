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


class VolatilityRegime(str, Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"


class StructureRegime(str, Enum):
    TRENDING = "TRENDING"
    RANGING = "RANGING"


class TradingSession(str, Enum):
    ASIA = "ASIA"
    LONDON = "LONDON"
    NEW_YORK = "NEW_YORK"
    OVERLAP = "OVERLAP"
    OFF = "OFF"


class SwingLifecycleState(str, Enum):
    """Explicit swing candidate lifecycle (Sprint 4)."""

    CANDIDATE = "CANDIDATE"
    POSSIBLE = "POSSIBLE"
    WAITING_CONFIRMATION = "WAITING_CONFIRMATION"
    CONFIRMED = "CONFIRMED"
    INVALIDATED = "INVALIDATED"
    REJECTED = "REJECTED"


class TrendBias(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    RANGING = "RANGING"


@dataclass
class SwingLifecycleEvent:
    bar_index: int
    state: SwingLifecycleState
    reason: str
    rule_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "bar_index": self.bar_index,
            "state": self.state.value,
            "reason": self.reason,
            "rule_id": self.rule_id,
            "metadata": to_dict(self.metadata),
        }


@dataclass
class SwingTrackedCandidate:
    """A pivot tracked through its full lifecycle."""

    swing_id: str
    pivot_index: int
    direction: SwingDirection
    price: float
    state: SwingLifecycleState = SwingLifecycleState.CANDIDATE
    events: list[SwingLifecycleEvent] = field(default_factory=list)
    final_swing: "DetectedSwing | None" = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "swing_id": self.swing_id,
            "pivot_index": self.pivot_index,
            "direction": self.direction.value,
            "price": self.price,
            "state": self.state.value,
            "events": [e.to_dict() for e in self.events],
            "final_swing": self.final_swing.to_dict() if self.final_swing else None,
        }


@dataclass
class SwingRuleCheck:
    """Single rule pass/fail for the Visualization Studio inspector."""

    rule_id: str
    label: str
    passed: bool
    value: str = ""
    threshold: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "label": self.label,
            "passed": self.passed,
            "value": self.value,
            "threshold": self.threshold,
        }


@dataclass
class MTFSwingContext:
    """Parent structure context for a lower-timeframe swing (Sprint 4)."""

    parent_timeframe: str | None = None
    parent_swing_id: str | None = None
    parent_trend: TrendBias = TrendBias.RANGING
    parent_external_high: float | None = None
    parent_external_low: float | None = None
    parent_dealing_range: tuple[float, float] | None = None
    parent_liquidity_high: float | None = None
    parent_liquidity_low: float | None = None
    alignment_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        dr = self.parent_dealing_range
        return {
            "parent_timeframe": self.parent_timeframe,
            "parent_swing_id": self.parent_swing_id,
            "parent_trend": self.parent_trend.value,
            "parent_external_high": self.parent_external_high,
            "parent_external_low": self.parent_external_low,
            "parent_dealing_range": list(dr) if dr else None,
            "parent_liquidity_high": self.parent_liquidity_high,
            "parent_liquidity_low": self.parent_liquidity_low,
            "alignment_score": round(self.alignment_score, 3),
        }


@dataclass
class MTFHierarchyResult:
    """Full multi-timeframe swing map for a symbol."""

    symbol: str
    hierarchy: list[str]
    swings_by_timeframe: dict[str, list["DetectedSwing"]]
    contexts: dict[str, MTFSwingContext]  # key: "TF:pivot_index:direction"

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "hierarchy": self.hierarchy,
            "swings_by_timeframe": {
                tf: [s.to_dict() for s in swings]
                for tf, swings in self.swings_by_timeframe.items()
            },
            "contexts": {k: v.to_dict() for k, v in self.contexts.items()},
        }


@dataclass(frozen=True)
class MarketContext:
    """Snapshot of market conditions used for adaptive detection."""

    volatility_regime: VolatilityRegime = VolatilityRegime.NORMAL
    structure_regime: StructureRegime = StructureRegime.RANGING
    session: TradingSession = TradingSession.OFF
    atr_percentile: float = 50.0
    efficiency_ratio: float = 0.0
    spread_atr_ratio: float = 0.0
    current_atr: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "volatility_regime": self.volatility_regime.value,
            "structure_regime": self.structure_regime.value,
            "session": self.session.value,
            "atr_percentile": round(self.atr_percentile, 1),
            "efficiency_ratio": round(self.efficiency_ratio, 3),
            "spread_atr_ratio": round(self.spread_atr_ratio, 3),
            "current_atr": round(self.current_atr, 6),
        }


@dataclass
class SwingExplanation:
    """Human-readable, structured explanation for a swing decision."""

    status: str = "accepted"  # accepted | rejected
    summary: str = ""
    factors: list[str] = field(default_factory=list)
    stage_scores: dict[str, float] = field(default_factory=dict)
    rejection_stage: str | None = None
    rejection_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "summary": self.summary,
            "factors": list(self.factors),
            "stage_scores": {k: round(v, 2) for k, v in self.stage_scores.items()},
            "rejection_stage": self.rejection_stage,
            "rejection_reason": self.rejection_reason,
        }


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
    quality_score: float = 0.0
    quality_factors: dict[str, float] = field(default_factory=dict)
    explanation: "SwingExplanation | None" = None
    rule_checks: list[SwingRuleCheck] = field(default_factory=list)
    lifecycle_state: SwingLifecycleState | None = None
    mtf_context: "MTFSwingContext | None" = None
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
            "quality_score": round(self.quality_score, 1),
            "quality_factors": {k: round(v, 1) for k, v in self.quality_factors.items()},
            "explanation": self.explanation.to_dict() if self.explanation else None,
            "rule_checks": [r.to_dict() for r in self.rule_checks],
            "lifecycle_state": self.lifecycle_state.value if self.lifecycle_state else None,
            "mtf_context": self.mtf_context.to_dict() if self.mtf_context else None,
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
    lifecycle_tracks: list[SwingTrackedCandidate] = field(default_factory=list)
    repainting_stats: dict[str, float] = field(default_factory=dict)
    atr_series: list[float] = field(default_factory=list)
    market_context: "MarketContext | None" = None

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
            "lifecycle_tracks": len(self.lifecycle_tracks),
            "repainting_stats": self.repainting_stats,
            "market_context": self.market_context.to_dict() if self.market_context else None,
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
    """Human or bootstrap ground-truth swing annotation.

    The first six fields preserve the v1 benchmark API.  The optional fields
    make labels confirmation-aware and auditable without breaking historical
    synthetic fixtures.
    """

    pivot_index: int
    timestamp: datetime
    price: float
    direction: SwingDirection
    tier: SwingTier = SwingTier.MAJOR
    scope: SwingScope = SwingScope.EXTERNAL
    label_id: str | None = None
    sample_id: str | None = None
    source_bar_index: int | None = None
    price_field: str | None = None
    confirmation_status: str = "CONFIRMED"
    confirmed_at_index: int | None = None
    confirmed_at_timestamp: datetime | None = None
    strength: int | None = None
    quality_score: float | None = None
    confidence: float | None = None
    tags: tuple[str, ...] = ()
    notes: str = ""
    annotator_id: str | None = None
    review_status: str = "RAW"


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
    major_external_precision: float = 0.0
    major_external_recall: float = 0.0
    major_external_f1: float = 0.0
    tier_accuracy: float = 0.0
    scope_accuracy: float = 0.0
    false_positives_per_1000_bars: float = 0.0
    average_relative_detection_delay_bars: float = 0.0
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
            "major_external_precision": round(self.major_external_precision, 4),
            "major_external_recall": round(self.major_external_recall, 4),
            "major_external_f1": round(self.major_external_f1, 4),
            "tier_accuracy": round(self.tier_accuracy, 4),
            "scope_accuracy": round(self.scope_accuracy, 4),
            "false_positives_per_1000_bars": round(self.false_positives_per_1000_bars, 4),
            "average_relative_detection_delay_bars": round(self.average_relative_detection_delay_bars, 2),
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

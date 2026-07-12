"""Confidence calibration — validate predicted confidence vs actual match rate."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from swing_engine.config import SwingEngineConfig
from swing_engine.evaluation import SwingBenchmarkEvaluator
from swing_engine.models import BenchmarkLabel, DetectedSwing, EvaluationReport


@dataclass
class CalibrationBucket:
    label: str
    confidence_min: float
    confidence_max: float
    predicted_confidence: float
    actual_accuracy: float
    count: int
    calibration_error: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "confidence_min": round(self.confidence_min, 2),
            "confidence_max": round(self.confidence_max, 2),
            "predicted_confidence": round(self.predicted_confidence, 3),
            "actual_accuracy": round(self.actual_accuracy, 3),
            "count": self.count,
            "calibration_error": round(self.calibration_error, 3),
        }


@dataclass
class CalibrationReport:
    buckets: list[CalibrationBucket] = field(default_factory=list)
    mean_calibration_error: float = 0.0
    total_swings: int = 0
    matched_swings: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_swings": self.total_swings,
            "matched_swings": self.matched_swings,
            "mean_calibration_error": round(self.mean_calibration_error, 4),
            "buckets": [b.to_dict() for b in self.buckets],
        }


def _matched_pivot_indices(report: EvaluationReport) -> set[int]:
    return {int(pair["predicted_index"]) for pair in report.matched_pairs}


def calibrate_confidence(
    predicted: list[DetectedSwing],
    ground_truth: list[BenchmarkLabel],
    config: SwingEngineConfig,
    *,
    symbol: str,
    n_buckets: int = 10,
) -> CalibrationReport:
    """Bucket swings by confidence decile and compare to ground-truth match rate."""
    confirmed = [s for s in predicted if s.confirmed]
    evaluator = SwingBenchmarkEvaluator(config)
    eval_report = evaluator.evaluate(confirmed, ground_truth, symbol)
    matched_idx = _matched_pivot_indices(eval_report)

    if not confirmed:
        return CalibrationReport()

    buckets: list[CalibrationBucket] = []
    step = 1.0 / n_buckets
    errors: list[float] = []

    for b in range(n_buckets):
        lo, hi = b * step, (b + 1) * step
        in_bucket = [
            s for s in confirmed
            if lo <= s.confidence < hi or (b == n_buckets - 1 and s.confidence == 1.0)
        ]
        if not in_bucket:
            continue
        hits = sum(1 for s in in_bucket if s.pivot_index in matched_idx)
        actual = hits / len(in_bucket)
        predicted_avg = sum(s.confidence for s in in_bucket) / len(in_bucket)
        err = abs(predicted_avg - actual)
        errors.append(err)
        buckets.append(CalibrationBucket(
            label=f"{int(lo * 100)}–{int(hi * 100)}%",
            confidence_min=lo,
            confidence_max=hi,
            predicted_confidence=predicted_avg,
            actual_accuracy=actual,
            count=len(in_bucket),
            calibration_error=err,
        ))

    return CalibrationReport(
        buckets=buckets,
        mean_calibration_error=sum(errors) / len(errors) if errors else 0.0,
        total_swings=len(confirmed),
        matched_swings=len(matched_idx),
    )

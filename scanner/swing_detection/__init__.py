"""Backward-compatible shim — canonical implementation is swing_engine."""

from typing import Any

from shared.types.models import Candle, Timeframe

from swing_engine import (
    SwingDetectionEngine,
    SwingDetectionOutput,
    SwingEvaluator,
    get_swing_detection_config,
)
from swing_engine.detector import SwingEngine
from swing_engine.models import (
    BenchmarkSwing,
    DetectionResult,
    EvaluationReport,
    InternalSwing as Swing,
    PivotCandidate,
    SwingClassification,
    SwingDirection,
    PipelineStageLog,
)


def detect_swings(
    bars: list[Candle],
    timeframe: Timeframe | None = None,
    **config_overrides: Any,
) -> DetectionResult:
    """Legacy API — returns full DetectionResult (not just swing list)."""
    tf = timeframe or (bars[0].timeframe if bars else Timeframe.H1)
    cfg = get_swing_detection_config(tf, **config_overrides) if config_overrides else get_swing_detection_config(tf)
    return SwingEngine(cfg).detect(bars, timeframe=tf)


__all__ = [
    "SwingDetectionEngine", "detect_swings", "get_swing_detection_config",
    "Swing", "SwingDirection", "SwingClassification", "PivotCandidate",
    "SwingDetectionOutput", "BenchmarkSwing", "EvaluationReport",
    "SwingEvaluator", "PipelineStageLog",
]

"""FX Navigators Swing Detection Engine — Sprint 1 foundation."""

from scanner.swing_detection.engine import SwingDetectionEngine, detect_swings
from scanner.swing_detection.evaluator import SwingEvaluator
from scanner.swing_detection.models import (
    BenchmarkSwing,
    EvaluationReport,
    PivotCandidate,
    Swing,
    SwingClassification,
    SwingDetectionOutput,
    SwingDirection,
)
from scanner.swing_detection.utils import SwingDetectionConfig, get_swing_detection_config

__all__ = [
    "SwingDetectionEngine",
    "detect_swings",
    "SwingEvaluator",
    "Swing",
    "SwingDirection",
    "SwingClassification",
    "SwingDetectionOutput",
    "PivotCandidate",
    "BenchmarkSwing",
    "EvaluationReport",
    "SwingDetectionConfig",
    "get_swing_detection_config",
]

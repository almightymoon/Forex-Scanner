"""Re-exports Swing Detection Engine from scanner.swing_detection."""

from scanner.swing_detection import (
    SwingDetectionEngine,
    SwingDetectionOutput,
    SwingEvaluator,
    detect_swings,
    get_swing_detection_config,
)
from scanner.swing_detection.models import (
    BenchmarkSwing,
    EvaluationReport,
    Swing,
    SwingClassification,
    SwingDirection,
)

SwingDetector = SwingDetectionEngine
SwingDetectionResult = SwingDetectionOutput
SwingSide = SwingDirection
SwingTier = SwingClassification

__all__ = [
    "SwingDetectionEngine",
    "SwingDetector",
    "detect_swings",
    "Swing",
    "SwingDirection",
    "SwingClassification",
    "SwingDetectionOutput",
    "SwingDetectionResult",
    "SwingSide",
    "SwingTier",
    "SwingEvaluator",
    "get_swing_detection_config",
    "BenchmarkSwing",
    "EvaluationReport",
]

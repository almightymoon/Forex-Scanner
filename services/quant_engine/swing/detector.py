"""Shim — use swing_engine."""

from swing_engine.detector import SwingDetectionEngine, SwingDetector, detect_swings
from swing_engine.models import DetectionResult as SwingDetectionResult

__all__ = ["SwingDetectionEngine", "SwingDetector", "detect_swings", "SwingDetectionResult"]

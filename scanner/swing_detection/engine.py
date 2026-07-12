"""Shim — use swing_engine.detector."""

from swing_engine.detector import SwingDetectionEngine, detect_swings
from swing_engine.models import DetectionResult as SwingDetectionOutput

__all__ = ["SwingDetectionEngine", "detect_swings", "SwingDetectionOutput"]

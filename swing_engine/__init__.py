"""Swing Detection Engine — standalone versioned component (Sprint 1)."""

from swing_engine.detector import SwingEngine, detect_swings
from swing_engine.config import SwingEngineConfig, get_config
from swing_engine.models import (
    BenchmarkLabel,
    DetectedSwing,
    DetectionResult,
    EvaluationReport,
    SwingDirection,
    SwingScope,
    SwingTier,
)
from swing_engine.evaluation import SwingBenchmarkEvaluator, write_csv_report, write_json_report
from swing_engine.visualization import SwingVisualizer

__version__ = "1.0.0"

__all__ = [
    "SwingEngine",
    "detect_swings",
    "SwingEngineConfig",
    "get_config",
    "DetectedSwing",
    "DetectionResult",
    "SwingDirection",
    "SwingTier",
    "SwingScope",
    "BenchmarkLabel",
    "EvaluationReport",
    "SwingBenchmarkEvaluator",
    "write_json_report",
    "write_csv_report",
    "SwingVisualizer",
]

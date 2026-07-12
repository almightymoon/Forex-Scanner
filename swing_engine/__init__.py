"""Swing Detection Engine — single source of truth."""

from swing_engine.detector import SwingEngine, SwingDetectionEngine, detect_swings
from swing_engine.config import SwingEngineConfig, SwingDetectionConfig, get_config, get_swing_detection_config
from swing_engine.models import (
    BenchmarkLabel, BenchmarkSwing, DetectedSwing, DetectionResult,
    EvaluationReport, InternalSwing, PivotCandidate, PipelineArtifacts,
    PerformanceMetrics, RejectedCandidate, Swing, SwingClassification,
    SwingDetectionOutput, SwingDirection, SwingScope, SwingTier,
)
from swing_engine.evaluation import (
    SwingBenchmarkEvaluator, SwingEvaluator,
    write_csv_report, write_json_report, write_markdown_report, write_comparison_charts,
)
from swing_engine.visualization import SwingVisualizer
from swing_engine.versions import DEFAULT_VERSION, SUPPORTED_VERSIONS

__version__ = "1.1.0"

__all__ = [
    "SwingEngine", "SwingDetectionEngine", "detect_swings",
    "SwingEngineConfig", "SwingDetectionConfig", "get_config", "get_swing_detection_config",
    "DetectedSwing", "DetectionResult", "SwingDirection", "SwingTier", "SwingScope",
    "BenchmarkLabel", "BenchmarkSwing", "EvaluationReport",
    "SwingBenchmarkEvaluator", "SwingEvaluator",
    "write_json_report", "write_csv_report", "write_markdown_report", "write_comparison_charts",
    "SwingVisualizer", "PipelineArtifacts", "PerformanceMetrics", "RejectedCandidate",
    "PivotCandidate", "DEFAULT_VERSION", "SUPPORTED_VERSIONS",
]

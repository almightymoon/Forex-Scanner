"""Swing Detection Engine — single source of truth."""

from swing_engine.detector import SwingEngine, SwingDetectionEngine, detect_swings
from swing_engine.config import SwingEngineConfig, SwingDetectionConfig, get_config, get_swing_detection_config
from swing_engine.models import (
    BenchmarkLabel, BenchmarkSwing, DetectedSwing, DetectionResult,
    EvaluationReport, InternalSwing, MarketContext, PivotCandidate, PipelineArtifacts,
    PerformanceMetrics, RejectedCandidate, StructureRegime, Swing, SwingClassification,
    SwingDetectionOutput, SwingDirection, SwingExplanation, SwingScope, SwingTier,
    TradingSession, VolatilityRegime,
)
from swing_engine.context import adapt_config, compute_market_context
from swing_engine.quality import compute_quality_score
from swing_engine.explain import build_swing_explanation, build_rejection_explanation
from swing_engine.live_validation import PaperSwingLog, LiveValidationResult, compare_against_review
from swing_engine.regression import append_history, load_history, write_regression_dashboard
from swing_engine.evaluation import (
    SwingBenchmarkEvaluator, SwingEvaluator,
    write_csv_report, write_json_report, write_markdown_report, write_comparison_charts,
)
from swing_engine.visualization import SwingVisualizer
from swing_engine.versions import DEFAULT_VERSION, SUPPORTED_VERSIONS

__version__ = "1.2.0"

__all__ = [
    "SwingEngine", "SwingDetectionEngine", "detect_swings",
    "SwingEngineConfig", "SwingDetectionConfig", "get_config", "get_swing_detection_config",
    "DetectedSwing", "DetectionResult", "SwingDirection", "SwingTier", "SwingScope",
    "BenchmarkLabel", "BenchmarkSwing", "EvaluationReport",
    "SwingBenchmarkEvaluator", "SwingEvaluator",
    "write_json_report", "write_csv_report", "write_markdown_report", "write_comparison_charts",
    "SwingVisualizer", "PipelineArtifacts", "PerformanceMetrics", "RejectedCandidate",
    "PivotCandidate", "DEFAULT_VERSION", "SUPPORTED_VERSIONS",
    "MarketContext", "SwingExplanation", "VolatilityRegime", "StructureRegime", "TradingSession",
    "compute_market_context", "adapt_config", "compute_quality_score",
    "build_swing_explanation", "build_rejection_explanation",
    "PaperSwingLog", "LiveValidationResult", "compare_against_review",
    "append_history", "load_history", "write_regression_dashboard",
]

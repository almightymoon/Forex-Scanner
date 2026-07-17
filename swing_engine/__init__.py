"""Swing Detection Engine — single source of truth."""

from swing_engine.detector import SwingEngine, SwingDetectionEngine, detect_swings
from swing_engine.config import SwingEngineConfig, SwingDetectionConfig, get_config, get_swing_detection_config
from swing_engine.models import (
    BenchmarkLabel, BenchmarkSwing, DetectedSwing, DetectionResult,
    EvaluationReport, InternalSwing, MTFHierarchyResult, MTFSwingContext,
    MarketContext, PivotCandidate, PipelineArtifacts,
    PerformanceMetrics, RejectedCandidate, StructureRegime, Swing, SwingClassification,
    SwingDetectionOutput, SwingDirection, SwingExplanation, SwingLifecycleState,
    SwingLifecycleEvent, SwingRuleCheck, SwingScope, SwingTier, SwingTrackedCandidate,
    TradingSession, TrendBias, VolatilityRegime,
)
from swing_engine.context import adapt_config, compute_market_context
from swing_engine.quality import compute_quality_score
from swing_engine.explain import build_swing_explanation, build_rejection_explanation
from swing_engine.lifecycle import build_lifecycle, compute_repainting_stats
from swing_engine.rules import build_rule_checks_for_swing, build_rule_checks_for_rejection
from swing_engine.mtf import detect_mtf_hierarchy, DEFAULT_HIERARCHY
from swing_engine.replay import SwingReplayEngine, SwingReplaySession, ReplayFrame
from swing_engine.optimizer import ParamGrid, OptimizationResult, run_optimization, save_optimization_report
from swing_engine.datasets import (
    BenchmarkSuiteReport,
    DatasetSpec,
    load_manifest,
    load_labels,
    load_real_bars,
    run_dataset,
    run_suite,
    write_labels,
)
from swing_engine.benchmark_data import (
    BenchmarkDataError,
    canonicalise_csv,
    load_candles_csv,
    sha256_file,
    write_canonical_candles_csv,
)
from swing_engine.benchmark_sampling import BenchmarkWindow, select_calibration_windows
from swing_engine.annotations import (
    AnnotationIssue,
    labels_from_document,
    load_annotation_document,
    validate_annotation_document,
    write_human_annotation_template,
)
from swing_engine.live_validation import PaperSwingLog, LiveValidationResult, compare_against_review
from swing_engine.regression import append_history, load_history, write_regression_dashboard, write_benchmark_dashboard
from swing_engine.evaluation import (
    SwingBenchmarkEvaluator, SwingEvaluator,
    write_csv_report, write_json_report, write_markdown_report, write_comparison_charts,
)
from swing_engine.calibration import CalibrationReport, calibrate_confidence
from swing_engine.confirmation_score import compute_score_breakdown
from swing_engine.ground_truth import labels_from_synthetic_bars, synthetic_pivot_indices, write_ground_truth_file
from swing_engine.structure_metadata import enrich_structure_metadata, swing_id
from swing_engine.visualization import SwingVisualizer
from swing_engine.versions import DEFAULT_VERSION, SUPPORTED_VERSIONS

__version__ = "2.0.0"

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
    "SwingLifecycleState", "SwingLifecycleEvent", "SwingTrackedCandidate", "SwingRuleCheck",
    "MTFSwingContext", "MTFHierarchyResult", "TrendBias",
    "compute_market_context", "adapt_config", "compute_quality_score",
    "build_swing_explanation", "build_rejection_explanation",
    "build_lifecycle", "compute_repainting_stats",
    "build_rule_checks_for_swing", "build_rule_checks_for_rejection",
    "detect_mtf_hierarchy", "DEFAULT_HIERARCHY",
    "SwingReplayEngine", "SwingReplaySession", "ReplayFrame",
    "ParamGrid", "OptimizationResult", "run_optimization", "save_optimization_report",
    "PaperSwingLog", "LiveValidationResult", "compare_against_review",
    "append_history", "load_history", "write_regression_dashboard", "write_benchmark_dashboard",
    "load_manifest", "load_labels", "load_real_bars", "write_labels", "run_dataset", "run_suite",
    "BenchmarkSuiteReport", "DatasetSpec",
    "BenchmarkDataError", "canonicalise_csv", "load_candles_csv", "sha256_file",
    "write_canonical_candles_csv", "BenchmarkWindow", "select_calibration_windows",
    "AnnotationIssue", "labels_from_document", "load_annotation_document",
    "validate_annotation_document", "write_human_annotation_template",
    "calibrate_confidence", "CalibrationReport",
    "compute_score_breakdown",
    "labels_from_synthetic_bars", "synthetic_pivot_indices", "write_ground_truth_file",
    "enrich_structure_metadata", "swing_id",
    "SwingVisualizer",
]

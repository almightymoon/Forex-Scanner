"""Shim — canonical implementation is swing_engine."""

from swing_engine import *  # noqa: F403
from swing_engine import (
    SwingEngine as SwingDetectionEngine,
    SwingEngine as SwingDetector,
    detect_swings,
    get_config as get_swing_detection_config,
    get_config as get_swing_config,
)
from swing_engine.models import (
    BenchmarkLabel as BenchmarkSwing,
    DetectedSwing,
    DetectionResult as SwingDetectionOutput,
    EvaluationReport,
    SwingDirection,
    SwingScope,
    SwingTier,
    SwingClassification,
    SwingSide,
)

from swing_engine.evaluation import SwingBenchmarkEvaluator as SwingEvaluator

from services.quant_engine.swing.analysis import (
    MarketStructureState,
    SwingPoint,
    TrendContext,
    analyze_market_structure,
    analyze_trend_context,
    build_zigzag_swings,
    classify_bos,
    detect_session_liquidity,
    find_swings,
    session_from_hour,
)
from swing_engine.visualization import SwingVisualizer

build_chart_overlay = SwingVisualizer().build

__all__ = [
    "SwingDetectionEngine", "SwingDetector", "detect_swings",
    "DetectedSwing", "SwingDirection", "SwingClassification", "SwingTier", "SwingScope", "SwingSide",
    "SwingDetectionOutput", "SwingEvaluator", "get_swing_detection_config", "get_swing_config",
    "build_chart_overlay", "SwingVisualizer",
    "SwingPoint", "MarketStructureState", "TrendContext",
    "build_zigzag_swings", "find_swings", "analyze_market_structure", "analyze_trend_context",
    "classify_bos", "session_from_hour", "detect_session_liquidity",
    "BenchmarkSwing", "EvaluationReport",
]

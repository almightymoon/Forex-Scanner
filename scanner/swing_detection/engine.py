"""
Swing Detection Engine — orchestrates the full pipeline.

Historical Candles → Pivots → Noise Filter → ATR Validation → Leg Validation
→ Confirmation → Strength → Classification → Output
"""

from __future__ import annotations

import logging
from typing import Any

from shared.types.models import Candle, Timeframe

from scanner.swing_detection.confirmation import confirm_swings
from scanner.swing_detection.filters import (
    apply_noise_filters,
    validate_atr_movement,
    validate_minimum_leg,
)
from scanner.swing_detection.models import PipelineStageLog, SwingDetectionOutput
from scanner.swing_detection.pivots import detect_pivot_candidates
from scanner.swing_detection.strength import classify_swings, score_all_swings
from scanner.swing_detection.utils import (
    SwingDetectionConfig,
    compute_atr_series,
    get_swing_detection_config,
    log_stage,
)

logger = logging.getLogger("fxnav.swing_detection.engine")


class SwingDetectionEngine:
    """Production swing detection — modular, deterministic, config-driven."""

    def __init__(self, config: SwingDetectionConfig | None = None):
        self._config = config

    def detect(
        self,
        candles: list[Candle],
        *,
        symbol: str | None = None,
        timeframe: Timeframe | None = None,
        config: SwingDetectionConfig | None = None,
    ) -> SwingDetectionOutput:
        """Run the full detection pipeline on historical candles."""
        cfg = config or self._config or get_swing_detection_config(
            timeframe or (candles[0].timeframe if candles else None)
        )
        stage_logs: list[PipelineStageLog] = []

        if not candles:
            tf = timeframe or Timeframe.H1
            sym = symbol or "UNKNOWN"
            return SwingDetectionOutput(swings=[], symbol=sym, timeframe=tf, candle_count=0)

        sym = symbol or candles[0].symbol
        tf = timeframe or candles[0].timeframe
        n = len(candles)
        atr_series = compute_atr_series(candles, cfg.atr.period)

        min_bars = cfg.pivot.left_lookback + cfg.pivot.right_lookback + cfg.confirmation.min_candles + 1
        if n < min_bars:
            log_stage("engine", n, 0, reason="insufficient_bars", min_bars=min_bars)
            return SwingDetectionOutput(
                swings=[],
                symbol=sym,
                timeframe=tf,
                candle_count=n,
                metadata={"reason": "insufficient_bars", "min_bars": min_bars},
            )

        # Stage 1: Candidate pivot detection
        candidates = detect_pivot_candidates(candles, cfg)
        stage_logs.append(
            PipelineStageLog("pivot_detection", n, len(candidates), n - len(candidates))
        )

        # Stage 2: Noise filtering
        filtered, noise_rejections = apply_noise_filters(candidates, candles, atr_series, cfg)
        stage_logs.append(
            PipelineStageLog(
                "noise_filter",
                len(candidates),
                len(filtered),
                len(candidates) - len(filtered),
                details=noise_rejections,
            )
        )

        # Stage 3: ATR validation
        atr_valid, atr_rejected = validate_atr_movement(filtered, candles, atr_series, cfg)
        stage_logs.append(
            PipelineStageLog(
                "atr_validation",
                len(filtered),
                len(atr_valid),
                atr_rejected,
            )
        )

        # Stage 4: Minimum leg validation
        leg_valid, leg_rejected = validate_minimum_leg(atr_valid, candles, atr_series, cfg)
        stage_logs.append(
            PipelineStageLog(
                "leg_validation",
                len(atr_valid),
                len(leg_valid),
                leg_rejected,
            )
        )

        # Stage 5: Swing confirmation
        swings = confirm_swings(leg_valid, candles, atr_series, cfg)
        stage_logs.append(
            PipelineStageLog(
                "confirmation",
                len(leg_valid),
                len(swings),
                0,
                details={"confirmed": sum(1 for s in swings if s.confirmed)},
            )
        )

        # Stage 6: Strength calculation
        swings = score_all_swings(swings, candles, atr_series, cfg)
        stage_logs.append(
            PipelineStageLog("strength", len(swings), len(swings), 0)
        )

        # Stage 7: Major / minor classification
        swings = classify_swings(swings, candles, atr_series, cfg)
        stage_logs.append(
            PipelineStageLog(
                "classification",
                len(swings),
                len(swings),
                0,
                details={
                    "major": sum(1 for s in swings if s.classification.value == "MAJOR"),
                    "minor": sum(1 for s in swings if s.classification.value == "MINOR"),
                },
            )
        )

        log_stage(
            "engine_complete",
            n,
            len(swings),
            symbol=sym,
            timeframe=tf.value,
            confirmed=sum(1 for s in swings if s.confirmed),
        )

        return SwingDetectionOutput(
            swings=swings,
            symbol=sym,
            timeframe=tf,
            candle_count=n,
            stage_logs=stage_logs,
            metadata={"config_source": "config/swing_detection.yaml"},
        )


def detect_swings(
    candles: list[Candle],
    timeframe: Timeframe | None = None,
    **config_overrides: Any,
) -> SwingDetectionOutput:
    """Functional entry point."""
    tf = timeframe or (candles[0].timeframe if candles else Timeframe.H1)
    cfg = get_swing_detection_config(tf)
    return SwingDetectionEngine(cfg).detect(candles, timeframe=tf)

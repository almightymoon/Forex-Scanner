"""
Swing Detection Engine — public API.

    bars → detect_swings() → List[DetectedSwing]
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
from scanner.swing_detection.pivots import detect_pivot_candidates
from scanner.swing_detection.utils import compute_atr_series, get_swing_detection_config, log_stage
from swing_engine.config import SwingEngineConfig, get_config
from swing_engine.models import DetectedSwing, DetectionResult
from swing_engine.scoring import score_and_classify

logger = logging.getLogger("fxnav.swing_engine")


class SwingEngine:
    """Standalone swing detection — config-driven, deterministic, modular."""

    def __init__(self, config: SwingEngineConfig | None = None):
        self._config = config

    def detect(
        self,
        bars: list[Candle],
        *,
        symbol: str | None = None,
        timeframe: Timeframe | None = None,
        config: SwingEngineConfig | None = None,
    ) -> DetectionResult:
        """Run full pipeline on OHLCV bars."""
        cfg = config or self._config or get_config(
            timeframe or (bars[0].timeframe if bars else None)
        )
        stage_logs: list[dict[str, Any]] = []

        if not bars:
            tf = timeframe or Timeframe.H1
            return DetectionResult(swings=[], symbol=symbol or "UNKNOWN", timeframe=tf, bar_count=0)

        sym = symbol or bars[0].symbol
        tf = timeframe or bars[0].timeframe
        atr_series = compute_atr_series(bars, cfg.atr.period)

        candidates = detect_pivot_candidates(bars, cfg)
        stage_logs.append({"stage": "pivots", "count": len(candidates)})

        filtered, rejections = apply_noise_filters(candidates, bars, atr_series, cfg)
        stage_logs.append({"stage": "noise_filter", "count": len(filtered), "rejections": rejections})

        atr_valid, atr_rej = validate_atr_movement(filtered, bars, atr_series, cfg)
        stage_logs.append({"stage": "atr_validation", "count": len(atr_valid), "rejected": atr_rej})

        leg_valid, leg_rej = validate_minimum_leg(atr_valid, bars, atr_series, cfg)
        stage_logs.append({"stage": "leg_validation", "count": len(leg_valid), "rejected": leg_rej})

        confirmed = confirm_swings(leg_valid, bars, atr_series, cfg)
        stage_logs.append({
            "stage": "confirmation",
            "count": len(confirmed),
            "confirmed": sum(1 for s in confirmed if s.confirmed),
        })

        detected = score_and_classify(confirmed, bars, atr_series, cfg)
        stage_logs.append({"stage": "scoring", "count": len(detected)})

        log_stage("engine_complete", len(bars), len(detected), symbol=sym, timeframe=tf.value)

        return DetectionResult(
            swings=detected,
            symbol=sym,
            timeframe=tf,
            bar_count=len(bars),
            stage_logs=stage_logs,
            metadata={"engine_version": "1.0.0", "config": "config/swing_detection.yaml"},
        )


def detect_swings(
    bars: list[Candle],
    timeframe: Timeframe | None = None,
    **config_overrides: Any,
) -> list[DetectedSwing]:
    """Functional API — returns detected swings from bars."""
    tf = timeframe or (bars[0].timeframe if bars else Timeframe.H1)
    cfg = get_config(tf, **config_overrides) if config_overrides else get_config(tf)
    return SwingEngine(cfg).detect(bars, timeframe=tf).swings

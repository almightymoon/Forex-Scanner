"""Swing Detection Engine v1.0.0 pipeline."""

from __future__ import annotations

from typing import Any

from shared.types.models import Candle, Timeframe

from swing_engine.config import SwingEngineConfig, get_config
from swing_engine.confirmation import confirm_swings
from swing_engine.filters import apply_noise_filters, validate_atr_movement, validate_minimum_leg
from swing_engine.models import DetectionResult, PipelineArtifacts
from swing_engine.performance import measure_performance
from swing_engine.pivots import detect_pivot_candidates
from swing_engine.scoring import score_and_classify
from swing_engine.utils import compute_atr_series, log_stage

VERSION = "1.0.0"


def detect_v1(
    bars: list[Candle],
    *,
    symbol: str | None = None,
    timeframe: Timeframe | None = None,
    config: SwingEngineConfig | None = None,
) -> DetectionResult:
    """v1 pipeline with full artifact capture."""
    cfg = config or get_config(timeframe or (bars[0].timeframe if bars else None))
    artifacts = PipelineArtifacts()
    stage_logs: list[dict[str, Any]] = []

    if not bars:
        tf = timeframe or Timeframe.H1
        return DetectionResult(swings=[], symbol=symbol or "UNKNOWN", timeframe=tf, bar_count=0, version=VERSION)

    sym = symbol or bars[0].symbol
    tf = timeframe or bars[0].timeframe

    with measure_performance(sym, tf.value, VERSION, len(bars)) as perf_ctx:
        atr_series = compute_atr_series(bars, cfg.atr.period)
        artifacts.atr_series = atr_series

        candidates = detect_pivot_candidates(bars, cfg)
        artifacts.pivot_candidates = candidates
        stage_logs.append({"stage": "pivots", "count": len(candidates)})

        filtered, noise_rej, noise_counts = apply_noise_filters(candidates, bars, atr_series, cfg)
        artifacts.noise_filtered = filtered
        artifacts.noise_rejected = noise_rej
        stage_logs.append({"stage": "noise_filter", "count": len(filtered), "rejections": noise_counts})

        atr_valid, atr_rej = validate_atr_movement(filtered, bars, atr_series, cfg)
        artifacts.atr_validated = atr_valid
        artifacts.atr_rejected = atr_rej
        stage_logs.append({"stage": "atr_validation", "count": len(atr_valid), "rejected": len(atr_rej)})

        leg_valid, leg_rej = validate_minimum_leg(atr_valid, bars, atr_series, cfg)
        artifacts.leg_validated = leg_valid
        artifacts.leg_rejected = leg_rej
        stage_logs.append({"stage": "leg_validation", "count": len(leg_valid), "rejected": len(leg_rej)})

        confirmed = confirm_swings(leg_valid, bars, atr_series, cfg)
        artifacts.confirmed_swings = [s for s in confirmed if s.confirmed]
        artifacts.unconfirmed_swings = [s for s in confirmed if not s.confirmed]
        stage_logs.append({
            "stage": "confirmation",
            "confirmed": len(artifacts.confirmed_swings),
            "unconfirmed": len(artifacts.unconfirmed_swings),
        })

        detected = score_and_classify(confirmed, bars, atr_series, cfg)
        perf_ctx["swing_count"] = len(detected)
        stage_logs.append({"stage": "scoring", "count": len(detected)})
        stage_logs.append({"stage": "complete", "count": len(detected), "version": VERSION})

    log_stage("v1_complete", len(bars), len(detected), symbol=sym)

    return DetectionResult(
        swings=detected,
        symbol=sym,
        timeframe=tf,
        bar_count=len(bars),
        version=VERSION,
        artifacts=artifacts,
        performance=perf_ctx.get("metrics"),
        stage_logs=stage_logs,
        metadata={"engine": "swing_engine", "version": VERSION},
    )

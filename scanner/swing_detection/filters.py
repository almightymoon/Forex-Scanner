"""Shim — backward-compatible filter API over swing_engine."""

from __future__ import annotations

from shared.types.models import Candle

from swing_engine.config import SwingEngineConfig
from swing_engine.models import PivotCandidate, RejectedCandidate
import swing_engine.filters as _filters


def apply_noise_filters(
    candidates: list[PivotCandidate],
    candles: list[Candle],
    atr_series: list[float],
    config: SwingEngineConfig,
) -> tuple[list[PivotCandidate], dict[str, int]]:
    kept, _rejected, stats = _filters.apply_noise_filters(candidates, candles, atr_series, config)
    return kept, stats


def validate_atr_movement(
    pivots: list[PivotCandidate],
    candles: list[Candle],
    atr_series: list[float],
    config: SwingEngineConfig,
) -> tuple[list[PivotCandidate], int]:
    kept, rejected = _filters.validate_atr_movement(pivots, candles, atr_series, config)
    return kept, len(rejected)


def validate_minimum_leg(
    pivots: list[PivotCandidate],
    candles: list[Candle],
    atr_series: list[float],
    config: SwingEngineConfig,
) -> tuple[list[PivotCandidate], int]:
    kept, rejected = _filters.validate_minimum_leg(pivots, candles, atr_series, config)
    return kept, len(rejected)


__all__ = ["apply_noise_filters", "validate_atr_movement", "validate_minimum_leg"]

"""Noise filtering and validation stages for pivot candidates."""

from __future__ import annotations

from shared.types.models import Candle

from scanner.swing_detection.models import PivotCandidate, SwingDirection
from scanner.swing_detection.utils import (
    SwingDetectionConfig,
    atr_at,
    log_stage,
    pips_to_price,
)


def apply_noise_filters(
    candidates: list[PivotCandidate],
    candles: list[Candle],
    atr_series: list[float],
    config: SwingDetectionConfig,
) -> tuple[list[PivotCandidate], dict[str, int]]:
    """Remove insignificant pivots — returns filtered list and rejection counts."""
    nf = config.noise_filter
    symbol = candles[0].symbol if candles else "EURUSD"
    rejections: dict[str, int] = {
        "candle_distance": 0,
        "pip_distance": 0,
        "atr_movement": 0,
        "consecutive_same": 0,
        "duplicate_level": 0,
    }

    if not candidates:
        return [], rejections

    min_pip_price = pips_to_price(nf.min_pip_distance, symbol, config)
    eq_tol = pips_to_price(nf.equal_level_tolerance_pips, symbol, config)

    sorted_cands = sorted(candidates, key=lambda p: p.pivot_index)
    kept: list[PivotCandidate] = []

    for pivot in sorted_cands:
        if kept:
            last = kept[-1]
            bar_dist = pivot.pivot_index - last.pivot_index
            if bar_dist < nf.min_candle_distance:
                rejections["candle_distance"] += 1
                continue

            price_dist = abs(pivot.price - last.price)
            if price_dist < min_pip_price:
                rejections["pip_distance"] += 1
                continue

            atr = atr_at(pivot.pivot_index, atr_series, candles)
            if price_dist < nf.min_atr_multiple * atr:
                rejections["atr_movement"] += 1
                continue

            if nf.dedupe_equal_levels and last.direction == pivot.direction:
                if abs(pivot.price - last.price) <= eq_tol:
                    if pivot.direction == SwingDirection.HIGH and pivot.price > last.price:
                        kept[-1] = pivot
                    elif pivot.direction == SwingDirection.LOW and pivot.price < last.price:
                        kept[-1] = pivot
                    else:
                        rejections["duplicate_level"] += 1
                    continue

            if nf.ignore_consecutive_same_direction and last.direction == pivot.direction:
                if pivot.direction == SwingDirection.HIGH and pivot.price >= last.price:
                    kept[-1] = pivot
                    rejections["consecutive_same"] += 1
                    continue
                if pivot.direction == SwingDirection.LOW and pivot.price <= last.price:
                    kept[-1] = pivot
                    rejections["consecutive_same"] += 1
                    continue
                rejections["consecutive_same"] += 1
                continue

        kept.append(pivot)

    log_stage("noise_filter", len(candidates), len(kept), rejections=rejections)
    return kept, rejections


def validate_atr_movement(
    pivots: list[PivotCandidate],
    candles: list[Candle],
    atr_series: list[float],
    config: SwingDetectionConfig,
) -> tuple[list[PivotCandidate], int]:
    """Reject pivots whose local move is below ATR multiplier × ATR."""
    multiplier = config.atr.validation_multiplier
    kept: list[PivotCandidate] = []
    rejected = 0

    for pivot in pivots:
        atr = atr_at(pivot.pivot_index, atr_series, candles)
        left = max(0, pivot.pivot_index - config.pivot.left_lookback)
        right = min(len(candles), pivot.pivot_index + config.pivot.right_lookback + 1)
        window = candles[left:right]
        if pivot.direction == SwingDirection.HIGH:
            local_move = pivot.price - min(c.low for c in window)
        else:
            local_move = max(c.high for c in window) - pivot.price

        if local_move >= multiplier * atr:
            kept.append(pivot)
        else:
            rejected += 1

    log_stage("atr_validation", len(pivots), len(kept), rejected=rejected, multiplier=multiplier)
    return kept, rejected


def validate_minimum_leg(
    pivots: list[PivotCandidate],
    candles: list[Candle],
    atr_series: list[float],
    config: SwingDetectionConfig,
) -> tuple[list[PivotCandidate], int]:
    """Require minimum leg size from previous opposite pivot (pips and ATR)."""
    symbol = candles[0].symbol if candles else "EURUSD"
    min_pip_price = pips_to_price(config.leg.min_pips, symbol, config)
    min_atr_mult = config.leg.min_atr_multiple

    kept: list[PivotCandidate] = []
    rejected = 0

    for pivot in pivots:
        if not kept:
            kept.append(pivot)
            continue

        prev = kept[-1]
        if prev.direction == pivot.direction:
            kept.append(pivot)
            continue

        leg = abs(pivot.price - prev.price)
        atr = atr_at(pivot.pivot_index, atr_series, candles)
        if leg >= min_pip_price and leg >= min_atr_mult * atr:
            kept.append(pivot)
        else:
            rejected += 1

    log_stage("leg_validation", len(pivots), len(kept), rejected=rejected)
    return kept, rejected

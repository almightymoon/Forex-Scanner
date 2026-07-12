"""Noise filtering and validation with rejection tracking."""

from __future__ import annotations

from shared.types.models import Candle

from swing_engine.config import SwingEngineConfig
from swing_engine.models import PivotCandidate, RejectedCandidate, SwingDirection
from swing_engine.utils import atr_at, log_stage, pips_to_price


def apply_noise_filters(
    candidates: list[PivotCandidate],
    candles: list[Candle],
    atr_series: list[float],
    config: SwingEngineConfig,
) -> tuple[list[PivotCandidate], list[RejectedCandidate], dict[str, int]]:
    nf = config.noise_filter
    symbol = candles[0].symbol if candles else "EURUSD"
    rejections: dict[str, int] = {
        "candle_distance": 0, "pip_distance": 0, "atr_movement": 0,
        "consecutive_same": 0, "duplicate_level": 0, "spread": 0,
        "volatility": 0, "consolidation": 0, "insignificant_pullback": 0,
    }
    rejected_list: list[RejectedCandidate] = []

    if not candidates:
        return [], rejected_list, rejections

    min_pip_price = pips_to_price(nf.min_pip_distance, symbol, config)
    eq_tol = pips_to_price(nf.equal_level_tolerance_pips, symbol, config)
    kept: list[PivotCandidate] = []

    for pivot in sorted(candidates, key=lambda p: p.pivot_index):
        reject = _reject_noise(pivot, kept, candles, atr_series, config, min_pip_price, eq_tol)
        if reject:
            stage, reason = reject
            rejections[reason] = rejections.get(reason, 0) + 1
            rejected_list.append(RejectedCandidate(pivot, stage, reason))
            continue
        kept.append(pivot)

    log_stage("noise_filter", len(candidates), len(kept), rejections=rejections)
    return kept, rejected_list, rejections


def _reject_noise(
    pivot: PivotCandidate,
    kept: list[PivotCandidate],
    candles: list[Candle],
    atr_series: list[float],
    config: SwingEngineConfig,
    min_pip_price: float,
    eq_tol: float,
) -> tuple[str, str] | None:
    nf = config.noise_filter
    if not kept:
        return _reject_standalone(pivot, candles, atr_series, config)

    last = kept[-1]
    bar_dist = pivot.pivot_index - last.pivot_index
    if bar_dist < nf.min_candle_distance:
        return "noise_filter", "candle_distance"

    price_dist = abs(pivot.price - last.price)
    if price_dist < min_pip_price:
        return "noise_filter", "pip_distance"

    atr = atr_at(pivot.pivot_index, atr_series, candles)
    if price_dist < nf.min_atr_multiple * atr:
        return "noise_filter", "atr_movement"

    if nf.spread_filter_enabled:
        c = candles[pivot.pivot_index]
        spread = (c.spread if c.spread is not None else (c.high - c.low) * 0.1)
        if spread > nf.max_spread_atr_ratio * atr:
            return "noise_filter", "spread"

    if nf.volatility_filter_enabled and atr < nf.min_volatility_atr:
        return "noise_filter", "volatility"

    if nf.consolidation_max_bars > 0 and bar_dist <= nf.consolidation_max_bars:
        seg = candles[last.pivot_index : pivot.pivot_index + 1]
        if seg:
            rng = max(c.high for c in seg) - min(c.low for c in seg)
            if rng < nf.min_atr_multiple * atr:
                return "noise_filter", "consolidation"

    if nf.insignificant_pullback_atr > 0 and last.direction != pivot.direction:
        if price_dist < nf.insignificant_pullback_atr * atr:
            return "noise_filter", "insignificant_pullback"

    if nf.dedupe_equal_levels and last.direction == pivot.direction:
        if abs(pivot.price - last.price) <= eq_tol:
            if pivot.direction == SwingDirection.HIGH and pivot.price > last.price:
                kept[-1] = pivot
            elif pivot.direction == SwingDirection.LOW and pivot.price < last.price:
                kept[-1] = pivot
            else:
                return "noise_filter", "duplicate_level"
            return None

    if nf.ignore_consecutive_same_direction and last.direction == pivot.direction:
        if pivot.direction == SwingDirection.HIGH and pivot.price >= last.price:
            kept[-1] = pivot
            return None
        if pivot.direction == SwingDirection.LOW and pivot.price <= last.price:
            kept[-1] = pivot
            return None
        return "noise_filter", "consecutive_same"

    return None


def _reject_standalone(
    pivot: PivotCandidate,
    candles: list[Candle],
    atr_series: list[float],
    config: SwingEngineConfig,
) -> tuple[str, str] | None:
    nf = config.noise_filter
    atr = atr_at(pivot.pivot_index, atr_series, candles)
    if nf.volatility_filter_enabled and atr < nf.min_volatility_atr:
        return "noise_filter", "volatility"
    if nf.spread_filter_enabled:
        c = candles[pivot.pivot_index]
        spread = (c.spread if c.spread is not None else (c.high - c.low) * 0.1)
        if spread > nf.max_spread_atr_ratio * atr:
            return "noise_filter", "spread"
    return None


def validate_atr_movement(
    pivots: list[PivotCandidate],
    candles: list[Candle],
    atr_series: list[float],
    config: SwingEngineConfig,
) -> tuple[list[PivotCandidate], list[RejectedCandidate]]:
    multiplier = config.atr.validation_multiplier
    kept: list[PivotCandidate] = []
    rejected: list[RejectedCandidate] = []

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
            rejected.append(RejectedCandidate(pivot, "atr_validation", f"move<{multiplier}*atr"))

    log_stage("atr_validation", len(pivots), len(kept), rejected=len(rejected))
    return kept, rejected


def validate_minimum_leg(
    pivots: list[PivotCandidate],
    candles: list[Candle],
    atr_series: list[float],
    config: SwingEngineConfig,
) -> tuple[list[PivotCandidate], list[RejectedCandidate]]:
    symbol = candles[0].symbol if candles else "EURUSD"
    min_pip_price = pips_to_price(config.leg.min_pips, symbol, config)
    min_atr_mult = config.leg.min_atr_multiple
    kept: list[PivotCandidate] = []
    rejected: list[RejectedCandidate] = []

    for pivot in pivots:
        if not kept:
            kept.append(pivot)
            continue
        prev = kept[-1]
        if prev.direction == pivot.direction:
            if not config.leg.validate_same_direction:
                kept.append(pivot)
                continue
            opp = _last_opposite(kept, pivot.direction)
            if opp is None:
                kept.append(pivot)
                continue
            leg = abs(pivot.price - opp.price)
        else:
            leg = abs(pivot.price - prev.price)
        atr = atr_at(pivot.pivot_index, atr_series, candles)
        if leg >= min_pip_price and leg >= min_atr_mult * atr:
            kept.append(pivot)
        else:
            rejected.append(RejectedCandidate(pivot, "leg_validation", "leg_too_small"))

    log_stage("leg_validation", len(pivots), len(kept), rejected=len(rejected))
    return kept, rejected


def _last_opposite(kept: list[PivotCandidate], direction: SwingDirection) -> PivotCandidate | None:
    for p in reversed(kept):
        if p.direction != direction:
            return p
    return None

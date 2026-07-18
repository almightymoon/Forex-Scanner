"""Candidate pivot detection with configurable equal-level tolerance."""

from __future__ import annotations

from shared.types.models import Candle

from swing_engine.config import SwingEngineConfig
from swing_engine.models import PivotCandidate, SwingDirection
from swing_engine.utils import atr_at, compute_atr_series, log_stage, pips_to_price


def detect_pivot_candidates(candles: list[Candle], config: SwingEngineConfig) -> list[PivotCandidate]:
    left = config.pivot.left_lookback
    right = config.pivot.right_lookback
    n = len(candles)

    if n < left + right + 1:
        log_stage("pivot_detection", 0, 0, reason="insufficient_bars")
        return []

    highs = [_pivot_high(c, config) for c in candles]
    lows = [_pivot_low(c, config) for c in candles]
    eq_tol = pips_to_price(config.pivot.equal_level_tolerance_pips, candles[0].symbol, config)
    atr_series = compute_atr_series(candles, config.atr.period)
    candidates: list[PivotCandidate] = []
    last_idx = -config.pivot.min_separation_bars

    for i in range(left, n - right):
        hi, lo = highs[i], lows[i]
        is_high = _is_pivot_high(i, highs, left, right, eq_tol, config.pivot.allow_equal_levels)
        is_low = _is_pivot_low(i, lows, left, right, eq_tol, config.pivot.allow_equal_levels)

        if i - last_idx < config.pivot.min_separation_bars:
            continue

        direction: SwingDirection | None = None
        price = 0.0
        if is_high and not is_low:
            direction, price = SwingDirection.HIGH, hi
        elif is_low and not is_high:
            direction, price = SwingDirection.LOW, lo
        elif is_high and is_low:
            c = candles[i]
            mid = (c.open + c.close) / 2
            if mid >= hi - (hi - lo) * 0.5:
                direction, price = SwingDirection.HIGH, hi
            else:
                direction, price = SwingDirection.LOW, lo

        if direction is None:
            continue

        strength = _pivot_strength(candles, i, direction, atr_series, config)
        if strength < config.pivot.min_pivot_strength:
            continue

        candidates.append(PivotCandidate(
            i, candles[i].timestamp, price, direction, strength=strength,
            metadata={
                "pivot_strength": round(strength, 2),
                "available_index": i + right,
            },
        ))
        last_idx = i

    log_stage("pivot_detection", n, len(candidates))
    return candidates


def _pivot_high(c: Candle, config: SwingEngineConfig) -> float:
    if config.pivot.use_body_extreme:
        return max(c.open, c.close)
    return c.high


def _pivot_low(c: Candle, config: SwingEngineConfig) -> float:
    if config.pivot.use_body_extreme:
        return min(c.open, c.close)
    return c.low


def _is_pivot_high(
    i: int, highs: list[float], left: int, right: int, eq_tol: float, allow_equal: bool,
) -> bool:
    hi = highs[i]
    if allow_equal:
        left_ok = all(hi >= highs[i - j] - eq_tol for j in range(1, left + 1))
        right_ok = all(hi >= highs[i + j] - eq_tol for j in range(1, right + 1))
        strict = any(hi > highs[i - j] for j in range(1, left + 1)) or any(
            hi > highs[i + j] for j in range(1, right + 1)
        )
        return left_ok and right_ok and strict
    return all(hi > highs[i - j] for j in range(1, left + 1)) and all(
        hi > highs[i + j] for j in range(1, right + 1)
    )


def _is_pivot_low(
    i: int, lows: list[float], left: int, right: int, eq_tol: float, allow_equal: bool,
) -> bool:
    lo = lows[i]
    if allow_equal:
        left_ok = all(lo <= lows[i - j] + eq_tol for j in range(1, left + 1))
        right_ok = all(lo <= lows[i + j] + eq_tol for j in range(1, right + 1))
        strict = any(lo < lows[i - j] for j in range(1, left + 1)) or any(
            lo < lows[i + j] for j in range(1, right + 1)
        )
        return left_ok and right_ok and strict
    return all(lo < lows[i - j] for j in range(1, left + 1)) and all(
        lo < lows[i + j] for j in range(1, right + 1)
    )


def _pivot_strength(
    candles: list[Candle],
    index: int,
    direction: SwingDirection,
    atr_series: list[float],
    config: SwingEngineConfig,
) -> float:
    c = candles[index]
    atr = atr_at(index, atr_series, candles)
    if atr <= 0:
        return 50.0
    body = abs(c.close - c.open)
    wick_up = c.high - max(c.open, c.close)
    wick_down = min(c.open, c.close) - c.low
    wick = wick_up if direction == SwingDirection.HIGH else wick_down
    body_atr = body / atr
    wick_atr = wick / atr
    return min(100.0, (body_atr * 40 + wick_atr * 60))

"""Candidate pivot detection — configurable left/right lookback."""

from __future__ import annotations

from shared.types.models import Candle

from scanner.swing_detection.models import PivotCandidate, SwingDirection
from scanner.swing_detection.utils import SwingDetectionConfig, log_stage


def detect_pivot_candidates(
    candles: list[Candle],
    config: SwingDetectionConfig,
) -> list[PivotCandidate]:
    """
    Detect pivot highs and lows.

    pivot_high if High[i] > High[i-left..i-1] and High[i] > High[i+1..i+right]
    pivot_low  if Low[i]  < Low[i-left..i-1]  and Low[i]  < Low[i+1..i+right]
    """
    left = config.pivot.left_lookback
    right = config.pivot.right_lookback
    n = len(candles)

    if n < left + right + 1:
        log_stage("pivot_detection", 0, 0, reason="insufficient_bars")
        return []

    highs = [c.high for c in candles]
    lows = [c.low for c in candles]
    candidates: list[PivotCandidate] = []

    for i in range(left, n - right):
        hi, lo = highs[i], lows[i]

        is_high = all(hi > highs[i - j] for j in range(1, left + 1)) and all(
            hi > highs[i + j] for j in range(1, right + 1)
        )
        is_low = all(lo < lows[i - j] for j in range(1, left + 1)) and all(
            lo < lows[i + j] for j in range(1, right + 1)
        )

        if is_high and not is_low:
            candidates.append(
                PivotCandidate(i, candles[i].timestamp, hi, SwingDirection.HIGH)
            )
        elif is_low and not is_high:
            candidates.append(
                PivotCandidate(i, candles[i].timestamp, lo, SwingDirection.LOW)
            )
        elif is_high and is_low:
            c = candles[i]
            mid = (c.open + c.close) / 2
            if mid >= hi - (hi - lo) * 0.5:
                candidates.append(PivotCandidate(i, candles[i].timestamp, hi, SwingDirection.HIGH))
            else:
                candidates.append(PivotCandidate(i, candles[i].timestamp, lo, SwingDirection.LOW))

    log_stage("pivot_detection", n, len(candidates), candidates=len(candidates))
    return candidates

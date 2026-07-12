"""Candidate pivot detection."""

from __future__ import annotations

from shared.types.models import Candle

from swing_engine.config import SwingEngineConfig
from swing_engine.models import PivotCandidate, SwingDirection
from swing_engine.utils import log_stage


def detect_pivot_candidates(candles: list[Candle], config: SwingEngineConfig) -> list[PivotCandidate]:
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
            candidates.append(PivotCandidate(i, candles[i].timestamp, hi, SwingDirection.HIGH))
        elif is_low and not is_high:
            candidates.append(PivotCandidate(i, candles[i].timestamp, lo, SwingDirection.LOW))
        elif is_high and is_low:
            c = candles[i]
            mid = (c.open + c.close) / 2
            if mid >= hi - (hi - lo) * 0.5:
                candidates.append(PivotCandidate(i, candles[i].timestamp, hi, SwingDirection.HIGH))
            else:
                candidates.append(PivotCandidate(i, candles[i].timestamp, lo, SwingDirection.LOW))

    log_stage("pivot_detection", n, len(candidates))
    return candidates

"""ATR and candle series utilities for swing detection."""

from __future__ import annotations

from shared.types.models import Candle


def compute_atr_series(candles: list[Candle], period: int = 14) -> list[float]:
    """Wilder-smoothed ATR at each index — O(n)."""
    n = len(candles)
    if n == 0:
        return []
    if n == 1:
        return [candles[0].high - candles[0].low]

    trs: list[float] = [candles[0].high - candles[0].low]
    for i in range(1, n):
        c, prev = candles[i], candles[i - 1]
        tr = max(c.high - c.low, abs(c.high - prev.close), abs(c.low - prev.close))
        trs.append(tr)

    atrs: list[float] = [trs[0]]
    for i in range(1, n):
        if i < period:
            atrs.append(sum(trs[: i + 1]) / (i + 1))
        elif i == period:
            atrs.append(sum(trs[1 : period + 1]) / period)
        else:
            prev_atr = atrs[-1]
            atrs.append((prev_atr * (period - 1) + trs[i]) / period)
    return atrs


def atr_at(candles: list[Candle], index: int, atr_series: list[float] | None = None) -> float:
    if atr_series and 0 <= index < len(atr_series):
        v = atr_series[index]
        return v if v > 0 else _fallback_atr(candles, index)
    return _fallback_atr(candles, index)


def _fallback_atr(candles: list[Candle], index: int) -> float:
    if not candles:
        return 0.0
    i = min(max(index, 0), len(candles) - 1)
    return max(candles[i].high - candles[i].low, 1e-9)

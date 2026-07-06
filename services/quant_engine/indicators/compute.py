"""Technical indicator calculations."""

import math
from typing import Optional

from shared.types.models import Candle, IndicatorValues, SignalDirection, Timeframe


def ema(values: list[float], period: int) -> list[Optional[float]]:
    if len(values) < period:
        return [None] * len(values)
    multiplier = 2 / (period + 1)
    result: list[Optional[float]] = [None] * (period - 1)
    sma = sum(values[:period]) / period
    result.append(sma)
    prev = sma
    for i in range(period, len(values)):
        val = (values[i] - prev) * multiplier + prev
        result.append(val)
        prev = val
    return result


def sma(values: list[float], period: int) -> list[Optional[float]]:
    result: list[Optional[float]] = []
    for i in range(len(values)):
        if i < period - 1:
            result.append(None)
        else:
            result.append(sum(values[i - period + 1 : i + 1]) / period)
    return result


def rsi(closes: list[float], period: int = 14) -> list[Optional[float]]:
    if len(closes) < period + 1:
        return [None] * len(closes)

    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(d, 0) for d in deltas]
    losses = [abs(min(d, 0)) for d in deltas]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    result: list[Optional[float]] = [None] * period
    if avg_loss == 0:
        result.append(100.0)
    else:
        rs = avg_gain / avg_loss
        result.append(100 - (100 / (1 + rs)))

    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            result.append(100.0)
        else:
            rs = avg_gain / avg_loss
            result.append(100 - (100 / (1 + rs)))

    return result


def macd(
    closes: list[float], fast: int = 12, slow: int = 26, signal_period: int = 9
) -> tuple[list[Optional[float]], list[Optional[float]], list[Optional[float]]]:
    ema_fast = ema(closes, fast)
    ema_slow = ema(closes, slow)
    macd_line: list[Optional[float]] = []
    for f, s in zip(ema_fast, ema_slow):
        if f is not None and s is not None:
            macd_line.append(f - s)
        else:
            macd_line.append(None)

    valid_macd = [v for v in macd_line if v is not None]
    signal_ema = ema(valid_macd, signal_period) if valid_macd else []

    signal_line: list[Optional[float]] = [None] * len(macd_line)
    histogram: list[Optional[float]] = [None] * len(macd_line)

    offset = len(macd_line) - len(valid_macd)
    for i, sig in enumerate(signal_ema):
        idx = offset + i
        if idx < len(macd_line) and sig is not None and macd_line[idx] is not None:
            signal_line[idx] = sig
            histogram[idx] = macd_line[idx] - sig

    return macd_line, signal_line, histogram


def atr(candles: list[Candle], period: int = 14) -> list[Optional[float]]:
    if len(candles) < 2:
        return [None] * len(candles)

    trs: list[float] = []
    for i in range(1, len(candles)):
        high = candles[i].high
        low = candles[i].low
        prev_close = candles[i - 1].close
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)

    result: list[Optional[float]] = [None]
    atr_vals = sma(trs, period)
    for v in atr_vals:
        result.append(v)
    return result


def adx(candles: list[Candle], period: int = 14) -> list[Optional[float]]:
    if len(candles) < period * 2:
        return [None] * len(candles)

    plus_dm: list[float] = []
    minus_dm: list[float] = []
    tr_list: list[float] = []

    for i in range(1, len(candles)):
        up = candles[i].high - candles[i - 1].high
        down = candles[i - 1].low - candles[i].low
        plus_dm.append(up if up > down and up > 0 else 0)
        minus_dm.append(down if down > up and down > 0 else 0)
        tr = max(
            candles[i].high - candles[i].low,
            abs(candles[i].high - candles[i - 1].close),
            abs(candles[i].low - candles[i - 1].close),
        )
        tr_list.append(tr)

    smooth_plus = sum(plus_dm[:period])
    smooth_minus = sum(minus_dm[:period])
    smooth_tr = sum(tr_list[:period])

    dx_values: list[float] = []
    for i in range(period, len(tr_list)):
        smooth_plus = smooth_plus - smooth_plus / period + plus_dm[i]
        smooth_minus = smooth_minus - smooth_minus / period + minus_dm[i]
        smooth_tr = smooth_tr - smooth_tr / period + tr_list[i]
        if smooth_tr > 0:
            plus_di = 100 * smooth_plus / smooth_tr
            minus_di = 100 * smooth_minus / smooth_tr
            di_sum = plus_di + minus_di
            if di_sum > 0:
                dx_values.append(100 * abs(plus_di - minus_di) / di_sum)

    adx_vals = sma(dx_values, period) if dx_values else []
    result: list[Optional[float]] = [None] * (len(candles) - len(adx_vals))
    result.extend(adx_vals)
    while len(result) < len(candles):
        result.insert(0, None)
    return result[: len(candles)]


def bollinger_bands(
    closes: list[float], period: int = 20, std_dev: float = 2.0
) -> tuple[list[Optional[float]], list[Optional[float]], list[Optional[float]]]:
    middle = sma(closes, period)
    upper: list[Optional[float]] = []
    lower: list[Optional[float]] = []

    for i in range(len(closes)):
        if middle[i] is None:
            upper.append(None)
            lower.append(None)
        else:
            window = closes[max(0, i - period + 1) : i + 1]
            variance = sum((x - middle[i]) ** 2 for x in window) / len(window)
            std = math.sqrt(variance)
            upper.append(middle[i] + std_dev * std)
            lower.append(middle[i] - std_dev * std)

    return upper, middle, lower


def vwap(candles: list[Candle]) -> list[Optional[float]]:
    cumulative_tp_vol = 0.0
    cumulative_vol = 0
    result: list[Optional[float]] = []

    for c in candles:
        tp = (c.high + c.low + c.close) / 3
        vol = c.volume or 1
        cumulative_tp_vol += tp * vol
        cumulative_vol += vol
        result.append(cumulative_tp_vol / cumulative_vol if cumulative_vol > 0 else None)

    return result


def stochastic(
    candles: list[Candle], k_period: int = 14, d_period: int = 3
) -> tuple[list[Optional[float]], list[Optional[float]]]:
    k_values: list[Optional[float]] = []
    for i in range(len(candles)):
        if i < k_period - 1:
            k_values.append(None)
        else:
            window = candles[i - k_period + 1 : i + 1]
            highest = max(c.high for c in window)
            lowest = min(c.low for c in window)
            if highest != lowest:
                k_values.append(100 * (candles[i].close - lowest) / (highest - lowest))
            else:
                k_values.append(50.0)

    valid_k = [v for v in k_values if v is not None]
    d_ema = sma(valid_k, d_period) if valid_k else []
    d_values: list[Optional[float]] = [None] * (len(k_values) - len(d_ema))
    d_values.extend(d_ema)
    return k_values, d_values


def compute_all(candles: list[Candle], symbol: str, timeframe: Timeframe) -> IndicatorValues:
    """Compute all indicators for the latest candle."""
    closes = [c.close for c in candles]
    last_idx = len(candles) - 1

    ema20 = ema(closes, 20)
    ema50 = ema(closes, 50)
    ema200 = ema(closes, 200)
    sma20 = sma(closes, 20)
    rsi_vals = rsi(closes)
    macd_line, macd_sig, macd_hist = macd(closes)
    atr_vals = atr(candles)
    adx_vals = adx(candles)
    bb_upper, bb_mid, bb_lower = bollinger_bands(closes)
    vwap_vals = vwap(candles)
    stoch_k, stoch_d = stochastic(candles)

    def last(vals: list[Optional[float]]) -> Optional[float]:
        return vals[last_idx] if vals and vals[last_idx] is not None else None

    return IndicatorValues(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=candles[-1].timestamp,
        ema_20=last(ema20),
        ema_50=last(ema50),
        ema_200=last(ema200),
        sma_20=last(sma20),
        rsi_14=last(rsi_vals),
        macd_line=last(macd_line),
        macd_signal=last(macd_sig),
        macd_histogram=last(macd_hist),
        atr_14=last(atr_vals),
        adx_14=last(adx_vals),
        vwap=last(vwap_vals),
        bb_upper=last(bb_upper),
        bb_middle=last(bb_mid),
        bb_lower=last(bb_lower),
        stoch_k=last(stoch_k),
        stoch_d=last(stoch_d),
    )

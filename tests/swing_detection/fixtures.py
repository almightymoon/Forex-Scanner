"""Shared fixtures for swing detection tests."""

from __future__ import annotations

from datetime import datetime, timedelta

from shared.types.models import Candle, Timeframe


def swing_candles(
    n: int,
    *,
    base: float = 1.10,
    wave: float = 0.004,
    trend: float = 0.00015,
    period: int = 12,
    symbol: str = "EURUSD",
    timeframe: Timeframe = Timeframe.H1,
    volume: int = 1000,
) -> list[Candle]:
    """Synthetic OHLC with clear alternating pivots."""
    start = datetime(2025, 1, 1)
    out: list[Candle] = []
    for i in range(n):
        phase = i % period
        half = max(period // 2, 1)
        if phase < half:
            close = base + i * trend + (phase / half) * wave
        else:
            close = base + i * trend + wave - ((phase - half) / half) * wave
        spread = 0.0006
        vol = volume + (i % 5) * 200
        out.append(
            Candle(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=start + timedelta(hours=i),
                open=close - spread * 0.3,
                high=close + spread,
                low=close - spread,
                close=close,
                volume=vol,
            )
        )
    return out


def range_candles(
    n: int, center: float = 1.10, amp: float = 0.003, timeframe: Timeframe = Timeframe.H1
) -> list[Candle]:
    return swing_candles(n, base=center, wave=amp * 2, trend=0.0, period=10, timeframe=timeframe)


def trend_candles(n: int, step: float = 0.002, timeframe: Timeframe = Timeframe.H1) -> list[Candle]:
    return swing_candles(n, wave=max(step * 3, 0.004), trend=step * 0.15, timeframe=timeframe)


def volatile_candles(n: int, seed: int = 42, timeframe: Timeframe = Timeframe.H1) -> list[Candle]:
    import random

    rng = random.Random(seed)
    start = datetime(2025, 1, 1)
    price = 1.10
    out: list[Candle] = []
    for i in range(n):
        price += rng.uniform(-0.008, 0.008)
        spread = 0.001
        out.append(
            Candle(
                symbol="EURUSD",
                timeframe=timeframe,
                timestamp=start + timedelta(hours=i),
                open=price,
                high=price + spread,
                low=price - spread,
                close=price,
                volume=1000 + i * 10,
            )
        )
    return out


def gold_candles(
    n: int = 200,
    *,
    base: float = 2350.0,
    wave: float = 6.0,
    trend: float = 0.4,
    period: int = 12,
    seed: int = 7,
) -> list[Candle]:
    """Synthetic XAUUSD (gold) OHLC — price ~2350, gold-scale swings.

    Gold moves in dollars, not fractional pips, so amplitudes are much larger
    than FX. Used to validate gold pip sizing and adaptive thresholds.
    """
    import random

    rng = random.Random(seed)
    start = datetime(2025, 1, 1)
    out: list[Candle] = []
    for i in range(n):
        phase = i % period
        half = max(period // 2, 1)
        if phase < half:
            close = base + i * trend + (phase / half) * wave
        else:
            close = base + i * trend + wave - ((phase - half) / half) * wave
        close += rng.uniform(-0.8, 0.8)
        spread = 0.9
        out.append(
            Candle(
                symbol="XAUUSD",
                timeframe=Timeframe.H1,
                timestamp=start + timedelta(hours=i),
                open=close - spread * 0.3,
                high=close + spread,
                low=close - spread,
                close=close,
                volume=1500 + (i % 5) * 250,
            )
        )
    return out


def news_spike_candles(n: int = 80) -> list[Candle]:
    cs = swing_candles(n, wave=0.003)
    idx = n // 2
    c = cs[idx]
    cs[idx] = Candle(
        symbol=c.symbol,
        timeframe=c.timeframe,
        timestamp=c.timestamp,
        open=c.open,
        high=c.high + 0.015,
        low=c.low,
        close=c.close + 0.012,
        volume=c.volume * 5,
    )
    return cs

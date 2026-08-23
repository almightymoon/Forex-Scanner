"""Golden analytical fixtures for integrity regression tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from shared.types.models import Candle, Timeframe


def _ts(i: int) -> datetime:
    return datetime(2024, 3, 4, tzinfo=timezone.utc) + timedelta(hours=i)


def make_candle(
    i: int,
    *,
    open_: float,
    high: float,
    low: float,
    close: float,
    symbol: str = "XAUUSD",
    timeframe: Timeframe = Timeframe.H1,
    volume: float = 100.0,
) -> Candle:
    return Candle(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=_ts(i),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


def ambiguous_sl_tp_bar(*, entry: float = 2650.0) -> Candle:
    """Single bar that trades through both SL and TP for a long."""
    return make_candle(0, open_=entry, high=entry + 5, low=entry - 5, close=entry)


def bullish_trend_candles(n: int = 120) -> list[Candle]:
    """Rising series suitable for structure/trend smoke tests."""
    out: list[Candle] = []
    price = 2600.0
    for i in range(n):
        o = price
        c = price + 0.8
        h = c + 0.4
        l = o - 0.3
        out.append(make_candle(i, open_=o, high=h, low=l, close=c))
        price = c
    return out


def bearish_trend_candles(n: int = 120) -> list[Candle]:
    out: list[Candle] = []
    price = 2700.0
    for i in range(n):
        o = price
        c = price - 0.8
        h = o + 0.3
        l = c - 0.4
        out.append(make_candle(i, open_=o, high=h, low=l, close=c))
        price = c
    return out

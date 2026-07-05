"""Shared test fixtures."""

from datetime import datetime, timedelta

from shared.types.models import Candle, IndicatorValues, Timeframe


def indicators(**kwargs) -> IndicatorValues:
    base = dict(symbol="EURUSD", timeframe=Timeframe.H1, timestamp=datetime(2025, 1, 1))
    base.update(kwargs)
    return IndicatorValues(**base)


def candles(closes: list[float], symbol: str = "EURUSD") -> list[Candle]:
    start = datetime(2025, 1, 1)
    return [
        Candle(
            symbol=symbol,
            timeframe=Timeframe.H1,
            timestamp=start + timedelta(hours=i),
            open=c,
            high=c + 0.001,
            low=c - 0.001,
            close=c,
            volume=1000,
        )
        for i, c in enumerate(closes)
    ]

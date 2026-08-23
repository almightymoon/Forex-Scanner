"""Session-aware trend (Asia range vs London/NY expansion)."""

from __future__ import annotations

from datetime import datetime, timedelta

from shared.types.models import Candle, IndicatorValues, Timeframe, TrendDirection

from services.quant_engine.trend.engine import TrendEngine
from services.quant_engine.trend.session_context import assess_session_trend


def _candle(ts: datetime, high: float, low: float, close: float | None = None) -> Candle:
    mid = close if close is not None else (high + low) / 2
    return Candle(
        symbol="XAUUSD",
        timeframe=Timeframe.H1,
        timestamp=ts,
        open=mid,
        high=high,
        low=low,
        close=mid if close is None else close,
        volume=100.0,
    )


def test_asia_expansion_bias_bullish():
    # Asia 00-07: tight range 100-101; London break above Asia high
    base = datetime(2024, 6, 3, 0, 0, 0)  # Monday
    candles: list[Candle] = []
    for h in range(8):
        candles.append(_candle(base + timedelta(hours=h), 101.0, 100.0, 100.5))
    # London hours: expand above Asia
    for h in range(8, 14):
        candles.append(
            _candle(base + timedelta(hours=h), 103.5, 100.8, 103.0)
        )
    result = assess_session_trend(candles)
    assert result.expansion_vs_asia is True
    assert result.bias_hint is TrendDirection.BULLISH
    assert result.score_delta > 0


def test_asia_session_favors_compression():
    base = datetime(2024, 6, 3, 0, 0, 0)
    candles = [
        _candle(base + timedelta(hours=h), 101.0, 100.0, 100.5) for h in range(6)
    ]
    result = assess_session_trend(candles)
    assert result.session == "asia"
    assert result.score_delta <= 0


def test_trend_engine_metadata_includes_session_trend():
    base = datetime(2024, 6, 3, 0, 0, 0)
    candles = [
        _candle(base + timedelta(hours=h), 100 + h * 0.1, 99.5 + h * 0.05)
        for h in range(30)
    ]
    indicators = IndicatorValues(
        symbol="XAUUSD",
        timeframe=Timeframe.H1,
        timestamp=candles[-1].timestamp,
        ema_20=candles[-1].close,
        ema_50=candles[-10].close,
        ema_200=candles[0].close,
        adx_14=20.0,
        rsi_14=50.0,
        macd_histogram=0.0,
        atr_14=1.0,
        bb_lower=candles[-1].close - 1,
        bb_middle=candles[-1].close,
        bb_upper=candles[-1].close + 1,
    )
    out = TrendEngine().run(candles, indicators)
    assert "session_trend" in out.metadata
    assert "session" in out.metadata["session_trend"]

"""Unit tests for independent scoring engines."""

import unittest
from datetime import datetime

from services.scanner_service.models import MomentumAnalysis
from services.scanner_service.momentum_engine import MomentumEngine, MAX_MOMENTUM
from services.scanner_service.score_engine import ScoreEngine, MAX_MTF, MAX_NEWS
from services.scanner_service.trend_engine import TrendEngine, MAX_TREND
from shared.types.models import (
    Candle,
    IndicatorValues,
    NewsContext,
    NewsImpact,
    SMCPattern,
    SignalDirection,
    Timeframe,
    TrendDirection,
)


def _indicators(**kwargs) -> IndicatorValues:
    base = dict(symbol="EURUSD", timeframe=Timeframe.H1, timestamp=datetime(2025, 1, 1))
    base.update(kwargs)
    return IndicatorValues(**base)


def _candles(closes: list[float]) -> list[Candle]:
    return [
        Candle(
            symbol="EURUSD",
            timeframe=Timeframe.H1,
            timestamp=datetime(2025, 1, 1, i),
            open=c,
            high=c + 0.001,
            low=c - 0.001,
            close=c,
            volume=1000,
        )
        for i, c in enumerate(closes)
    ]


class TestTrendEngine(unittest.TestCase):
    def test_bullish_ema_alignment_scores_high(self):
        engine = TrendEngine()
        indicators = _indicators(ema_20=1.12, ema_50=1.11, ema_200=1.10, adx_14=30)
        candles = _candles([1.10 + i * 0.001 for i in range(12)])

        result = engine.analyze(candles, indicators)

        self.assertEqual(result.direction, TrendDirection.BULLISH)
        self.assertTrue(result.ema_aligned)
        self.assertGreaterEqual(result.score, 13)
        self.assertLessEqual(result.score, MAX_TREND)
        self.assertTrue(any("EMA" in r for r in result.reasons))

    def test_no_alignment_caps_score(self):
        engine = TrendEngine()
        indicators = _indicators()
        candles = _candles([1.10] * 5)

        result = engine.analyze(candles, indicators)

        self.assertEqual(result.score, 0)
        self.assertEqual(result.direction, TrendDirection.RANGING)


class TestMomentumEngine(unittest.TestCase):
    def test_bullish_momentum_in_zone(self):
        engine = MomentumEngine()
        indicators = _indicators(macd_histogram=0.5, rsi_14=60, atr_14=0.002)

        result = engine.analyze(indicators, TrendDirection.BULLISH)

        self.assertEqual(result.score, MAX_MOMENTUM)
        self.assertEqual(len(result.reasons), 3)

    def test_bearish_rsi_zone(self):
        engine = MomentumEngine()
        indicators = _indicators(rsi_14=40)

        result = engine.analyze(indicators, TrendDirection.BEARISH)

        self.assertTrue(result.rsi_in_zone)
        self.assertTrue(any("RSI" in r for r in result.reasons))


class TestScoreEngine(unittest.TestCase):
    def test_mtf_full_alignment(self):
        engine = ScoreEngine()
        trends = {
            "M15": TrendDirection.BULLISH,
            "H1": TrendDirection.BULLISH,
            "H4": TrendDirection.BULLISH,
            "D1": TrendDirection.BULLISH,
        }

        mtf = engine.analyze_mtf(trends, TrendDirection.BULLISH)

        self.assertTrue(mtf.aligned)
        self.assertEqual(mtf.score, MAX_MTF)

    def test_news_high_impact_soon_scores_zero(self):
        engine = ScoreEngine()
        news = NewsContext(has_high_impact_soon=True, minutes_until_event=15)

        self.assertEqual(engine.score_news(news), 0)

    def test_news_clear_scores_max(self):
        engine = ScoreEngine()
        news = NewsContext(has_high_impact_soon=False, impact=NewsImpact.LOW)

        self.assertEqual(engine.score_news(news), MAX_NEWS)

    def test_breakdown_total_sums_correctly(self):
        engine = ScoreEngine()
        breakdown = engine.build_breakdown(18, 24, 11, 5, 3, 10, 10)

        self.assertEqual(breakdown.total, 81)
        self.assertEqual(breakdown.trend, 18)
        self.assertEqual(breakdown.smc, 24)

    def test_direction_follows_trend_and_smc(self):
        engine = ScoreEngine()
        smc = [SMCPattern(pattern_type="BOS", direction=SignalDirection.BUY, strength=0.8)]
        momentum = MomentumAnalysis(score=10)
        direction = engine.determine_direction(TrendDirection.BULLISH, smc, momentum)

        self.assertEqual(direction, SignalDirection.BUY)


if __name__ == "__main__":
    unittest.main()

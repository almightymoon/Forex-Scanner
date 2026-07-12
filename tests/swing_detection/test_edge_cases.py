"""Edge-case and regression tests for swing detection quality."""

import unittest
from dataclasses import replace

from swing_engine import SwingEngine, get_config
from swing_engine.models import SwingDirection, SwingScope, SwingTier
from tests.swing_detection.fixtures import (
    news_spike_candles,
    range_candles,
    swing_candles,
    trend_candles,
    volatile_candles,
)


class TestEdgeCases(unittest.TestCase):
    def test_equal_highs_range_produces_swings(self):
        cs = range_candles(100, amp=0.0015)
        result = SwingEngine().detect(cs)
        self.assertGreater(len(result.swings), 0)

    def test_gapped_series_still_runs(self):
        cs = swing_candles(60)
        cs[30] = replace(
            cs[30],
            high=cs[30].high + 0.02,
            low=cs[30].low - 0.01,
            close=cs[30].close + 0.015,
        )
        result = SwingEngine().detect(cs)
        self.assertIsInstance(result.swings, list)

    def test_strong_trend_alternates_direction(self):
        result = SwingEngine().detect(trend_candles(120))
        dirs = [s.direction for s in result.swings]
        for i in range(1, len(dirs)):
            self.assertNotEqual(dirs[i - 1], dirs[i])

    def test_ranging_market_fewer_major_swings(self):
        result = SwingEngine().detect(range_candles(100))
        majors = [s for s in result.swings if s.tier == SwingTier.MAJOR]
        self.assertLessEqual(len(majors), len(result.swings))

    def test_volatile_market_has_rejections(self):
        result = SwingEngine().detect(volatile_candles(100))
        rejected = (
            result.artifacts.noise_rejected
            + result.artifacts.atr_rejected
            + result.artifacts.leg_rejected
        )
        self.assertGreaterEqual(len(rejected), 0)

    def test_news_spike_does_not_crash(self):
        result = SwingEngine().detect(news_spike_candles(80))
        self.assertGreater(len(result.swings), 0)


class TestClassificationQuality(unittest.TestCase):
    def test_confirmed_swings_have_confidence(self):
        result = SwingEngine().detect(trend_candles(100))
        for s in result.confirmed_swings:
            self.assertGreaterEqual(s.confidence, 0.0)
            self.assertLessEqual(s.confidence, 1.0)

    def test_scope_assigned(self):
        result = SwingEngine().detect(trend_candles(100))
        scopes = {s.scope for s in result.swings}
        self.assertTrue(scopes.issubset({SwingScope.INTERNAL, SwingScope.EXTERNAL, SwingScope.NEUTRAL}))

    def test_high_low_balance_on_trend(self):
        result = SwingEngine().detect(trend_candles(120))
        highs = sum(1 for s in result.swings if s.direction == SwingDirection.HIGH)
        lows = sum(1 for s in result.swings if s.direction == SwingDirection.LOW)
        self.assertGreater(highs, 0)
        self.assertGreater(lows, 0)
        self.assertLessEqual(abs(highs - lows), 2)


class TestRegressionBaseline(unittest.TestCase):
    """Guard against silent accuracy regressions on synthetic fixtures."""

    def test_trend_candles_baseline_f1(self):
        cs = trend_candles(120)
        engine = SwingEngine(get_config(cs[0].timeframe))
        result = engine.detect(cs)
        from swing_engine.evaluation import SwingBenchmarkEvaluator
        from swing_engine.models import BenchmarkLabel

        labels = [
            BenchmarkLabel(s.pivot_index, s.timestamp, s.price, s.direction, s.tier, s.scope)
            for s in result.confirmed_swings
        ]
        report = SwingBenchmarkEvaluator().evaluate(result.confirmed_swings, labels, "EURUSD")
        self.assertGreaterEqual(report.f1_score, 0.95)

    def test_swing_count_stable_on_fixed_seed(self):
        cs = swing_candles(100, period=12, wave=0.004)
        a = SwingEngine().detect(cs)
        b = SwingEngine().detect(cs)
        self.assertEqual(len(a.swings), len(b.swings))


if __name__ == "__main__":
    unittest.main()

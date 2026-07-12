"""Integration tests for the full swing detection engine."""

import time
import unittest

from shared.types.models import Timeframe

from swing_engine import SwingEngine, get_config
from swing_engine.models import SwingDirection
from tests.swing_detection.fixtures import (
    news_spike_candles,
    range_candles,
    swing_candles,
    trend_candles,
    volatile_candles,
)


def _detect(candles, timeframe=None):
    tf = timeframe or candles[0].timeframe
    return SwingEngine(get_config(tf)).detect(candles, timeframe=tf)


class TestSwingDetectionEngine(unittest.TestCase):
    def test_strong_trend(self):
        cs = trend_candles(120)
        out = _detect(cs)
        self.assertGreater(len(out.swings), 4)
        self.assertEqual(len(out.stage_logs), 7)

    def test_range_market(self):
        cs = range_candles(100)
        out = _detect(cs)
        self.assertGreater(len(out.swings), 0)

    def test_high_volatility(self):
        cs = volatile_candles(120)
        out = _detect(cs)
        self.assertGreater(len(out.swings), 2)

    def test_low_volatility(self):
        cs = swing_candles(80, wave=0.001, trend=0.00001)
        out = _detect(cs)
        self.assertIsInstance(out.swings, list)

    def test_equal_highs_range(self):
        cs = range_candles(80, amp=0.002)
        out = _detect(cs)
        highs = [s for s in out.swings if s.direction == SwingDirection.HIGH]
        self.assertGreater(len(highs), 0)

    def test_news_spike(self):
        cs = news_spike_candles(80)
        out = _detect(cs)
        self.assertGreater(len(out.swings), 0)

    def test_multi_timeframe(self):
        for tf in (Timeframe.M1, Timeframe.M15, Timeframe.H1, Timeframe.H4, Timeframe.D1):
            cs = swing_candles(100, timeframe=tf)
            out = SwingEngine(get_config(tf)).detect(cs, timeframe=tf)
            self.assertGreater(len(out.swings), 2, msg=tf.value)

    def test_deterministic_output(self):
        cs = trend_candles(80)
        a = _detect(cs)
        b = _detect(cs)
        self.assertEqual(
            [(s.pivot_index, s.price, s.confirmed) for s in a.swings],
            [(s.pivot_index, s.price, s.confirmed) for s in b.swings],
        )

    def test_performance_ten_thousand_candles(self):
        cs = swing_candles(10_000, period=16, wave=0.003, trend=0.00005, timeframe=Timeframe.M1)
        engine = SwingEngine(get_config(Timeframe.M1))
        engine.detect(cs[:200])
        start = time.perf_counter()
        out = engine.detect(cs)
        elapsed = time.perf_counter() - start
        self.assertGreater(len(out.swings), 10)
        self.assertLess(elapsed, 3.0)

    def test_output_to_dict(self):
        out = _detect(trend_candles(60))
        d = out.to_dict()
        self.assertIn("swings", d)
        self.assertIn("stage_logs", d)


if __name__ == "__main__":
    unittest.main()

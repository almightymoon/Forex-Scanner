"""Tests for pivot candidate detection."""

import unittest

from swing_engine.pivots import detect_pivot_candidates
from swing_engine import get_config
from tests.swing_detection.fixtures import swing_candles, trend_candles


class TestPivotDetection(unittest.TestCase):
    def test_detects_pivots_on_trend(self):
        cs = trend_candles(80)
        cfg = get_config(cs[0].timeframe)
        pivots = detect_pivot_candidates(cs, cfg)
        self.assertGreater(len(pivots), 4)

    def test_equal_levels_when_enabled(self):
        from dataclasses import replace
        cs = trend_candles(80)
        cfg = replace(get_config(cs[0].timeframe), pivot=replace(
            get_config(cs[0].timeframe).pivot, allow_equal_levels=True,
        ))
        pivots = detect_pivot_candidates(cs, cfg)
        self.assertGreater(len(pivots), 0)


if __name__ == "__main__":
    unittest.main()

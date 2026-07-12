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

    def test_alternating_directions(self):
        cs = swing_candles(100)
        cfg = get_config(cs[0].timeframe)
        pivots = detect_pivot_candidates(cs, cfg)
        for i in range(1, len(pivots)):
            self.assertNotEqual(pivots[i - 1].direction, pivots[i].direction)


if __name__ == "__main__":
    unittest.main()

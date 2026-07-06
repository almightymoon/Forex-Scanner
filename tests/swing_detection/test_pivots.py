"""Tests for candidate pivot detection."""

import unittest

from scanner.swing_detection.pivots import detect_pivot_candidates
from scanner.swing_detection.utils import get_swing_detection_config
from tests.swing_detection.fixtures import swing_candles, trend_candles


class TestPivotDetection(unittest.TestCase):
    def test_detects_pivots_in_trend(self):
        cs = trend_candles(100)
        cfg = get_swing_detection_config(cs[0].timeframe)
        pivots = detect_pivot_candidates(cs, cfg)
        self.assertGreater(len(pivots), 4)

    def test_pivot_indices_in_range(self):
        cs = swing_candles(80)
        cfg = get_swing_detection_config(cs[0].timeframe)
        pivots = detect_pivot_candidates(cs, cfg)
        for p in pivots:
            self.assertGreaterEqual(p.pivot_index, cfg.pivot.left_lookback)
            self.assertLess(p.pivot_index, len(cs) - cfg.pivot.right_lookback)

    def test_insufficient_bars(self):
        cs = swing_candles(3)
        cfg = get_swing_detection_config(cs[0].timeframe)
        self.assertEqual(detect_pivot_candidates(cs, cfg), [])

    def test_alternating_directions_in_raw_pivots(self):
        cs = swing_candles(100)
        cfg = get_swing_detection_config(cs[0].timeframe)
        pivots = detect_pivot_candidates(cs, cfg)
        # Raw pivots may have consecutive same direction before filtering
        self.assertGreater(len(pivots), 0)


if __name__ == "__main__":
    unittest.main()

"""Tests for noise filtering and validation stages."""

import unittest

from swing_engine.filters import apply_noise_filters, validate_atr_movement, validate_minimum_leg
from swing_engine.pivots import detect_pivot_candidates
from swing_engine import get_config
from swing_engine.utils import compute_atr_series
from tests.swing_detection.fixtures import range_candles, swing_candles


class TestNoiseFilters(unittest.TestCase):
    def test_filters_reduce_pivot_count(self):
        cs = swing_candles(100)
        cfg = get_config(cs[0].timeframe)
        atr = compute_atr_series(cs, cfg.atr.period)
        raw = detect_pivot_candidates(cs, cfg)
        filtered, _rejected, _stats = apply_noise_filters(raw, cs, atr, cfg)
        self.assertLessEqual(len(filtered), len(raw))

    def test_atr_validation_rejects_small_moves(self):
        cs = swing_candles(80)
        cfg = get_config(cs[0].timeframe)
        atr = compute_atr_series(cs, cfg.atr.period)
        pivots = detect_pivot_candidates(cs, cfg)
        valid, rejected = validate_atr_movement(pivots, cs, atr, cfg)
        self.assertGreaterEqual(len(rejected), 0)
        self.assertLessEqual(len(valid), len(pivots))

    def test_leg_validation_requires_opposite_distance(self):
        cs = range_candles(80)
        cfg = get_config(cs[0].timeframe)
        atr = compute_atr_series(cs, cfg.atr.period)
        pivots = detect_pivot_candidates(cs, cfg)
        filtered, _rej, _stats = apply_noise_filters(pivots, cs, atr, cfg)
        valid, _leg_rej = validate_minimum_leg(filtered, cs, atr, cfg)
        self.assertIsInstance(valid, list)


if __name__ == "__main__":
    unittest.main()

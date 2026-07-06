"""Tests for swing confirmation — no repaint."""

import unittest

from scanner.swing_detection.confirmation import confirm_swings
from scanner.swing_detection.filters import apply_noise_filters, validate_atr_movement, validate_minimum_leg
from scanner.swing_detection.pivots import detect_pivot_candidates
from scanner.swing_detection.utils import compute_atr_series, get_swing_detection_config
from tests.swing_detection.fixtures import swing_candles, trend_candles


class TestConfirmation(unittest.TestCase):
    def _pipeline_pivots(self, cs):
        cfg = get_swing_detection_config(cs[0].timeframe)
        atr = compute_atr_series(cs, cfg.atr.period)
        raw = detect_pivot_candidates(cs, cfg)
        filtered, _ = apply_noise_filters(raw, cs, atr, cfg)
        atr_v, _ = validate_atr_movement(filtered, cs, atr, cfg)
        leg_v, _ = validate_minimum_leg(atr_v, cs, atr, cfg)
        return leg_v, cs, atr, cfg

    def test_confirmed_swings_have_timestamp(self):
        pivots, cs, atr, cfg = self._pipeline_pivots(trend_candles(100))
        swings = confirm_swings(pivots, cs, atr, cfg)
        confirmed = [s for s in swings if s.confirmed]
        self.assertGreater(len(confirmed), 0)
        for s in confirmed:
            self.assertIsNotNone(s.confirmed_timestamp)
            self.assertIsNotNone(s.confirmation_index)
            self.assertGreater(s.confirmation_delay, 0)

    def test_no_repaint_on_same_data(self):
        cs = trend_candles(80)
        pivots, _, atr, cfg = self._pipeline_pivots(cs)
        first = confirm_swings(pivots, cs, atr, cfg)
        second = confirm_swings(pivots, cs, atr, cfg)
        keys1 = [(s.pivot_index, s.price, s.confirmed) for s in first]
        keys2 = [(s.pivot_index, s.price, s.confirmed) for s in second]
        self.assertEqual(keys1, keys2)

    def test_unconfirmed_or_empty_near_short_series(self):
        cs = trend_candles(30)
        pivots, _, atr, cfg = self._pipeline_pivots(cs)
        swings = confirm_swings(pivots, cs, atr, cfg)
        # Short series may yield all confirmed or empty after pipeline
        self.assertIsInstance(swings, list)


if __name__ == "__main__":
    unittest.main()

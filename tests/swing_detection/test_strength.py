"""Tests for strength scoring and classification."""

import unittest

from swing_engine.confirmation import confirm_swings
from swing_engine.filters import apply_noise_filters, validate_atr_movement, validate_minimum_leg
from swing_engine.pivots import detect_pivot_candidates
from swing_engine.scoring import score_and_classify
from swing_engine.strength import score_all_swings
from swing_engine import get_config
from swing_engine.utils import compute_atr_series
from swing_engine.models import SwingClassification
from tests.swing_detection.fixtures import swing_candles, trend_candles


class TestStrength(unittest.TestCase):
    def _full_swings(self, cs):
        cfg = get_config(cs[0].timeframe)
        atr = compute_atr_series(cs, cfg.atr.period)
        raw = detect_pivot_candidates(cs, cfg)
        filtered, _rej, _stats = apply_noise_filters(raw, cs, atr, cfg)
        atr_v, _atr_rej = validate_atr_movement(filtered, cs, atr, cfg)
        leg_v, _leg_rej = validate_minimum_leg(atr_v, cs, atr, cfg)
        swings = confirm_swings(leg_v, cs, atr, cfg)
        return score_all_swings(swings, cs, atr, cfg), cs, atr, cfg

    def test_strength_in_range_1_to_5(self):
        swings, _, _, _ = self._full_swings(trend_candles(100))
        for s in swings:
            self.assertGreaterEqual(s.strength, 1)
            self.assertLessEqual(s.strength, 5)

    def test_reasoning_populated(self):
        swings, _, _, _ = self._full_swings(trend_candles(80))
        self.assertGreater(len(swings[0].reasoning), 0)

    def test_classification_major_minor(self):
        swings, cs, atr, cfg = self._full_swings(trend_candles(150))
        classified = score_and_classify(swings, cs, atr, cfg)
        tiers = {s.classification for s in classified}
        self.assertTrue(tiers.issubset({SwingClassification.MAJOR, SwingClassification.MINOR}))


if __name__ == "__main__":
    unittest.main()

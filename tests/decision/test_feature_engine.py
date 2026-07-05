"""Tests for feature extraction and robust swing detection."""

import unittest

from services.feature_engine import FeatureExtractor
from services.scanner_service.swing_analysis import (
    analyze_market_structure,
    build_zigzag_swings,
    find_swings,
)
from shared.types.models import SMCPattern, SignalDirection
from tests.helpers import candles, indicators


def _wavy_closes(n: int = 60) -> list[float]:
    return [1.10 + (i % 6) * 0.002 + i * 0.0002 for i in range(n)]


class TestZigzagSwings(unittest.TestCase):
    def test_zigzag_alternates_high_low(self):
        cs = candles(_wavy_closes(50))
        swings = build_zigzag_swings(cs)
        for i in range(1, len(swings)):
            self.assertNotEqual(swings[i].kind, swings[i - 1].kind)

    def test_swing_strength_bounded(self):
        cs = candles(_wavy_closes(50))
        for s in build_zigzag_swings(cs):
            self.assertGreaterEqual(s.strength, 0)
            self.assertLessEqual(s.strength, 100)

    def test_market_structure_from_swings(self):
        cs = candles(_wavy_closes(60))
        state = analyze_market_structure(cs)
        self.assertIsNotNone(state.direction)
        self.assertGreaterEqual(len(state.swings), 0)


class TestFeatureExtractor(unittest.TestCase):
    def test_extract_produces_normalized_features(self):
        cs = candles(_wavy_closes(60))
        ind = indicators(ema_20=1.12, ema_50=1.11, atr_14=0.002, adx_14=28, rsi_14=58)
        patterns = [
            SMCPattern(pattern_type="bos", direction=SignalDirection.BUY, strength=75),
            SMCPattern(pattern_type="order_block", direction=SignalDirection.BUY, metadata={"index": 40, "impulse_ratio": 2.0}),
        ]
        features = FeatureExtractor().extract(cs, ind, patterns)
        self.assertGreater(features.swing_count, 0)
        self.assertIn("trend_direction", features.to_dict())
        self.assertEqual(features.ob_count, 1)

    def test_ob_quality_in_features(self):
        cs = candles(_wavy_closes(60))
        ind = indicators(atr_14=0.002)
        patterns = [
            SMCPattern(
                pattern_type="order_block",
                direction=SignalDirection.BUY,
                price_low=1.11,
                price_high=1.12,
                metadata={"index": 55, "impulse_ratio": 2.2},
            ),
        ]
        features = FeatureExtractor().extract(cs, ind, patterns)
        self.assertIsNotNone(features.best_ob)
        self.assertGreater(features.best_ob.overall, 0)


if __name__ == "__main__":
    unittest.main()

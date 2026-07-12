"""Tests for tier/scope classification and confidence scoring."""

import unittest

from swing_engine import SwingEngine, get_config
from swing_engine.scoring import classify_scope, classify_tier, compute_confidence
from swing_engine.models import DetectedSwing, SwingDirection, SwingScope, SwingTier
from tests.swing_detection.fixtures import trend_candles


class TestClassification(unittest.TestCase):
    def test_major_tier_on_large_leg(self):
        cfg = get_config()
        swing = DetectedSwing(
            timestamp=trend_candles(1)[0].timestamp, price=1.11, direction=SwingDirection.HIGH,
            tier=SwingTier.MINOR, scope=SwingScope.NEUTRAL, pivot_index=10,
            confirmed=True, strength=5, score=80, normalized_score=80,
        )
        tier = classify_tier(swing, leg_atr=1.5, reaction_atr=1.0, duration=12, config=cfg)
        self.assertEqual(tier, SwingTier.MAJOR)

    def test_minor_tier_on_small_leg(self):
        cfg = get_config()
        swing = DetectedSwing(
            timestamp=trend_candles(1)[0].timestamp, price=1.10, direction=SwingDirection.LOW,
            tier=SwingTier.MINOR, scope=SwingScope.NEUTRAL, pivot_index=5,
            confirmed=True, strength=2, score=30, normalized_score=30,
        )
        tier = classify_tier(swing, leg_atr=0.5, reaction_atr=0.3, duration=4, config=cfg)
        self.assertEqual(tier, SwingTier.MINOR)

    def test_external_scope_on_higher_high(self):
        cfg = get_config()
        prev_same = DetectedSwing(
            timestamp=trend_candles(1)[0].timestamp, price=1.10, direction=SwingDirection.HIGH,
            tier=SwingTier.MAJOR, scope=SwingScope.EXTERNAL, pivot_index=5, confirmed=True,
        )
        swing = DetectedSwing(
            timestamp=trend_candles(1)[0].timestamp, price=1.12, direction=SwingDirection.HIGH,
            tier=SwingTier.MAJOR, scope=SwingScope.NEUTRAL, pivot_index=15, confirmed=True,
        )
        scope = classify_scope(swing, prev_same, None, 1.11, 1.09, cfg)
        self.assertIn(scope, (SwingScope.EXTERNAL, SwingScope.NEUTRAL))

    def test_confidence_higher_when_confirmed(self):
        cfg = get_config()
        confirmed = DetectedSwing(
            timestamp=trend_candles(1)[0].timestamp, price=1.10, direction=SwingDirection.HIGH,
            tier=SwingTier.MAJOR, scope=SwingScope.EXTERNAL, pivot_index=5,
            confirmed=True, normalized_score=70, strength=4,
        )
        unconfirmed = DetectedSwing(
            timestamp=trend_candles(1)[0].timestamp, price=1.10, direction=SwingDirection.HIGH,
            tier=SwingTier.MAJOR, scope=SwingScope.EXTERNAL, pivot_index=5,
            confirmed=False, normalized_score=70, strength=4,
        )
        self.assertGreater(compute_confidence(confirmed, cfg), compute_confidence(unconfirmed, cfg))


class TestPipelineClassification(unittest.TestCase):
    def test_pipeline_assigns_scope_and_tier(self):
        result = SwingEngine(version="1.1.0").detect(trend_candles(100))
        tiers = {s.tier for s in result.swings}
        scopes = {s.scope for s in result.swings}
        self.assertTrue(tiers.issubset({SwingTier.MAJOR, SwingTier.MINOR}))
        self.assertTrue(scopes.issubset({SwingScope.INTERNAL, SwingScope.EXTERNAL, SwingScope.NEUTRAL}))


if __name__ == "__main__":
    unittest.main()

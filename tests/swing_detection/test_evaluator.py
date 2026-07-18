"""Tests for swing evaluation against benchmark labels."""

import unittest
from datetime import datetime

from swing_engine import SwingEngine, get_config
from swing_engine.evaluation import SwingBenchmarkEvaluator
from swing_engine.models import BenchmarkLabel, SwingDirection
from tests.swing_detection.fixtures import trend_candles


class TestSwingEvaluator(unittest.TestCase):
    def test_perfect_match_metrics(self):
        cs = trend_candles(100)
        cfg = get_config(cs[0].timeframe)
        out = SwingEngine(cfg).detect(cs)
        confirmed = [s for s in out.swings if s.confirmed]

        benchmark = [
            BenchmarkLabel(s.pivot_index, s.timestamp, s.price, s.direction)
            for s in confirmed
        ]

        report = SwingBenchmarkEvaluator(cfg).evaluate(confirmed, benchmark, "EURUSD")
        self.assertEqual(report.true_positives, len(confirmed))
        self.assertEqual(report.false_positives, 0)
        self.assertEqual(report.false_negatives, 0)
        self.assertAlmostEqual(report.precision, 1.0)
        self.assertAlmostEqual(report.recall, 1.0)
        self.assertAlmostEqual(report.f1_score, 1.0)

    def test_false_positive_detection(self):
        cfg = get_config()
        predicted = []
        benchmark = [
            BenchmarkLabel(10, datetime(2025, 1, 1), 1.10, SwingDirection.HIGH),
        ]
        report = SwingBenchmarkEvaluator(cfg).evaluate(predicted, benchmark, "EURUSD")
        self.assertEqual(report.false_negatives, 1)
        self.assertEqual(report.recall, 0.0)

    def test_report_to_dict(self):
        cfg = get_config()
        report = SwingBenchmarkEvaluator(cfg).evaluate([], [], "EURUSD")
        d = report.to_dict()
        self.assertIn("f1_score", d)
        self.assertIn("average_price_error_pips", d)


if __name__ == "__main__":
    unittest.main()


def test_semantic_metrics_and_human_confirmation_delay():
    from swing_engine.models import DetectedSwing, SwingScope, SwingTier

    cfg = get_config()
    predicted = [
        DetectedSwing(
            timestamp=datetime(2025, 1, 1),
            price=1.10,
            direction=SwingDirection.HIGH,
            tier=SwingTier.MINOR,
            scope=SwingScope.INTERNAL,
            pivot_index=10,
            confirmed=True,
            confirmation_index=14,
            confirmation_delay=4,
        )
    ]
    truth = [
        BenchmarkLabel(
            pivot_index=10,
            timestamp=datetime(2025, 1, 1),
            price=1.10,
            direction=SwingDirection.HIGH,
            tier=SwingTier.MAJOR,
            scope=SwingScope.EXTERNAL,
            confirmed_at_index=12,
        )
    ]
    report = SwingBenchmarkEvaluator(cfg).evaluate(
        predicted, truth, "EURUSD", bar_count=100
    )
    assert report.f1_score == 1.0  # pivot location/direction matched
    assert report.major_external_f1 == 0.0  # structural classification did not
    assert report.semantic_true_positives == 0
    assert report.semantic_precision == 0.0
    assert report.semantic_recall == 0.0
    assert report.semantic_f1 == 0.0
    assert report.tier_accuracy == 0.0
    assert report.scope_accuracy == 0.0
    assert report.average_relative_detection_delay_bars == 2.0

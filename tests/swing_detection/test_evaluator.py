"""Tests for swing evaluation against benchmark labels."""

import unittest
from datetime import datetime

from scanner.swing_detection import SwingDetectionEngine, SwingEvaluator, get_swing_detection_config
from scanner.swing_detection.models import BenchmarkSwing, SwingDirection
from tests.swing_detection.fixtures import trend_candles


class TestSwingEvaluator(unittest.TestCase):
    def test_perfect_match_metrics(self):
        cs = trend_candles(100)
        cfg = get_swing_detection_config(cs[0].timeframe)
        out = SwingDetectionEngine(cfg).detect(cs)
        confirmed = [s for s in out.swings if s.confirmed]

        benchmark = [
            BenchmarkSwing(s.pivot_index, s.timestamp, s.price, s.direction)
            for s in confirmed
        ]

        report = SwingEvaluator(cfg).evaluate(confirmed, benchmark, "EURUSD")
        self.assertEqual(report.true_positives, len(confirmed))
        self.assertEqual(report.false_positives, 0)
        self.assertEqual(report.false_negatives, 0)
        self.assertAlmostEqual(report.precision, 1.0)
        self.assertAlmostEqual(report.recall, 1.0)
        self.assertAlmostEqual(report.f1_score, 1.0)

    def test_false_positive_detection(self):
        cfg = get_swing_detection_config()
        predicted = []
        benchmark = [
            BenchmarkSwing(10, datetime(2025, 1, 1), 1.10, SwingDirection.HIGH),
        ]
        report = SwingEvaluator(cfg).evaluate(predicted, benchmark, "EURUSD")
        self.assertEqual(report.false_negatives, 1)
        self.assertEqual(report.recall, 0.0)

    def test_report_to_dict(self):
        cfg = get_swing_detection_config()
        report = SwingEvaluator(cfg).evaluate([], [], "EURUSD")
        d = report.to_dict()
        self.assertIn("f1_score", d)
        self.assertIn("average_price_error_pips", d)


if __name__ == "__main__":
    unittest.main()

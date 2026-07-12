"""Tests for swing_engine standalone package."""

import unittest

from shared.types.models import Timeframe

from swing_engine import SwingEngine, SwingVisualizer, detect_swings, get_config
from swing_engine.evaluation import SwingBenchmarkEvaluator, write_csv_report, write_json_report
from swing_engine.models import BenchmarkLabel, SwingDirection, SwingScope, SwingTier
from tests.swing_detection.fixtures import trend_candles, volatile_candles


class TestSwingEngine(unittest.TestCase):
    def test_detect_swings_returns_list(self):
        bars = trend_candles(100)
        swings = detect_swings(bars)
        self.assertGreater(len(swings), 3)

    def test_detected_swing_has_required_fields(self):
        swings = detect_swings(trend_candles(80))
        s = swings[0]
        self.assertIn(s.direction, (SwingDirection.HIGH, SwingDirection.LOW))
        self.assertIn(s.tier, (SwingTier.MAJOR, SwingTier.MINOR))
        self.assertIn(s.scope, (SwingScope.INTERNAL, SwingScope.EXTERNAL, SwingScope.NEUTRAL))
        self.assertGreaterEqual(s.strength, 1)
        self.assertGreaterEqual(s.confidence, 0.0)

    def test_deterministic(self):
        bars = trend_candles(80)
        a = detect_swings(bars)
        b = detect_swings(bars)
        self.assertEqual(
            [(s.pivot_index, s.price, s.confirmed) for s in a],
            [(s.pivot_index, s.price, s.confirmed) for s in b],
        )


class TestSwingVisualizer(unittest.TestCase):
    def test_build_with_window(self):
        bars = trend_candles(80)
        swings = detect_swings(bars)
        viz = SwingVisualizer().build(
            bars, swings,
            window_start=bars[10].timestamp,
            window_end=bars[50].timestamp,
        )
        self.assertIn("candlesticks", viz)
        self.assertIn("swings", viz)
        self.assertIn("confirmation_markers", viz)


class TestSwingBenchmark(unittest.TestCase):
    def test_evaluation_reports(self):
        bars = trend_candles(100)
        result = SwingEngine(get_config()).detect(bars)
        labels = [
            BenchmarkLabel(s.pivot_index, s.timestamp, s.price, s.direction, s.tier, s.scope)
            for s in result.confirmed_swings
        ]
        report = SwingBenchmarkEvaluator().evaluate(result.confirmed_swings, labels, "EURUSD")
        self.assertEqual(report.precision, 1.0)
        self.assertEqual(report.recall, 1.0)

    def test_json_csv_export(self, tmp_path=None):
        import tempfile
        from pathlib import Path

        bars = trend_candles(60)
        result = SwingEngine().detect(bars)
        labels = [
            BenchmarkLabel(s.pivot_index, s.timestamp, s.price, s.direction)
            for s in result.confirmed_swings
        ]
        report = SwingBenchmarkEvaluator().evaluate(result.confirmed_swings, labels, "EURUSD")

        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            write_json_report(report, d / "report.json")
            write_csv_report(report, d / "report.csv")
            self.assertTrue((d / "report.json").exists())
            self.assertTrue((d / "report.csv").exists())


class TestVolatileMarket(unittest.TestCase):
    def test_volatile_detection(self):
        swings = detect_swings(volatile_candles(100))
        self.assertGreater(len(swings), 2)


if __name__ == "__main__":
    unittest.main()

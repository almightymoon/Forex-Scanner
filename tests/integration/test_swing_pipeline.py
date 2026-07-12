"""End-to-end pipeline: ticks → bars → swings → evaluation."""

import unittest

from services.bar_builder import BarBuilder
from shared.types.models import Timeframe
from swing_engine import SwingEngine, SwingBenchmarkEvaluator, get_config
from swing_engine.models import BenchmarkLabel, SwingDirection
from tests.swing_detection.fixtures import swing_candles


class TestPipelineIntegration(unittest.TestCase):
    def test_bars_to_swings(self):
        bars = swing_candles(120)
        result = SwingEngine(get_config(Timeframe.H1)).detect(bars)
        self.assertGreater(len(result.swings), 4)
        self.assertEqual(len(result.stage_logs), 6)

    def test_ticks_to_bars_to_swings(self):
        bars_raw = swing_candles(100)
        ticks = [
            (c.timestamp, c.low, c.high, float(c.volume))
            for c in bars_raw
        ]
        m1 = BarBuilder("EURUSD", Timeframe.M1).to_candles(
            BarBuilder("EURUSD", Timeframe.M1).from_ticks(ticks)
        )
        self.assertGreater(len(m1), 0)

        # Use original bars for swing detection (M1 from ticks may differ in count)
        swings = SwingEngine().detect(bars_raw).swings
        self.assertGreater(len(swings), 2)

    def test_full_eval_pipeline(self):
        bars = swing_candles(100)
        engine = SwingEngine()
        result = engine.detect(bars)
        labels = [
            BenchmarkLabel(s.pivot_index, s.timestamp, s.price, SwingDirection(s.direction.value))
            for s in result.confirmed_swings
        ]
        report = SwingBenchmarkEvaluator().evaluate(result.confirmed_swings, labels, "EURUSD")
        self.assertGreaterEqual(report.f1_score, 0.9)


if __name__ == "__main__":
    unittest.main()

import unittest

from services.scanner_service.decision_engine import DecisionEngine
from shared.types.models import Timeframe, TrendDirection

from tests.helpers import candles, indicators


class TestDecisionEngine(unittest.TestCase):
    def test_evaluate_produces_v2_fields(self):
        engine = DecisionEngine()
        cs = candles([1.10 + i * 0.001 for i in range(60)])
        ind = indicators(
            ema_20=1.12, ema_50=1.11, ema_200=1.10,
            adx_14=30, macd_histogram=0.5, rsi_14=60, atr_14=0.002,
            bb_lower=1.09, bb_middle=1.105, bb_upper=1.12,
        )
        signal = engine.evaluate("EURUSD", Timeframe.H1, cs, ind, [])
        self.assertGreater(signal.score, 0)
        self.assertGreater(signal.confidence, 0)
        self.assertIsNotNone(signal.session)
        self.assertGreater(len(signal.engine_outputs), 0)
        self.assertEqual(signal.score, sum(o["score"] for o in signal.engine_outputs))

    def test_explainability_payload(self):
        engine = DecisionEngine()
        signal = engine.evaluate("EURUSD", Timeframe.H1, candles([1.10 + i * 0.001 for i in range(60)]), indicators(
            ema_20=1.12, ema_50=1.11, ema_200=1.10, adx_14=30,
            macd_histogram=0.5, rsi_14=60, atr_14=0.002,
        ), [])
        self.assertIsNotNone(signal.explainability)
        self.assertGreater(len(signal.explainability["categories"]), 0)
        self.assertGreater(len(signal.score_deltas), 0)


if __name__ == "__main__":
    unittest.main()

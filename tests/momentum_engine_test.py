import unittest

from services.scanner_service.momentum_engine import MomentumEngine, MAX_MOMENTUM
from shared.types.models import TrendDirection

from tests.helpers import indicators


class TestMomentumEngine(unittest.TestCase):
    def test_bullish_momentum_max_score(self):
        engine = MomentumEngine()
        result = engine.analyze(
            indicators(macd_histogram=0.5, rsi_14=60, atr_14=0.002),
            TrendDirection.BULLISH,
        )
        self.assertEqual(result.score, MAX_MOMENTUM)
        self.assertEqual(len(result.reasons), 3)

    def test_bearish_rsi_zone(self):
        engine = MomentumEngine()
        result = engine.analyze(indicators(rsi_14=40), TrendDirection.BEARISH)
        self.assertTrue(result.rsi_in_zone)
        self.assertTrue(any("RSI" in r for r in result.reasons))


if __name__ == "__main__":
    unittest.main()

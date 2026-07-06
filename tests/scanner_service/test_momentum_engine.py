import unittest

from services.scanner_service.momentum_engine import MomentumEngine
from shared.config.scoring_loader import get_v2_scoring_config
from shared.types.models import TrendDirection

from tests.helpers import indicators


class TestMomentumEngine(unittest.TestCase):
    def test_bullish_momentum_max_score(self):
        cfg = get_v2_scoring_config()
        engine = MomentumEngine()
        result = engine.run(60, indicators(macd_histogram=0.5, rsi_14=60, atr_14=0.002))
        self.assertEqual(result.score, cfg.weights.momentum)

    def test_bearish_rsi_zone(self):
        engine = MomentumEngine()
        result = engine.analyze(indicators(rsi_14=40), TrendDirection.BEARISH)
        self.assertTrue(result.rsi_in_zone)


if __name__ == "__main__":
    unittest.main()

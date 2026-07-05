import unittest

from services.scanner_service.trend_engine import TrendEngine
from shared.config.scoring_loader import get_v2_scoring_config
from shared.types.models import TrendDirection

from tests.helpers import candles, indicators


class TestTrendEngine(unittest.TestCase):
    def test_bullish_ema_alignment_scores_high(self):
        cfg = get_v2_scoring_config()
        engine = TrendEngine()
        result = engine.run(
            candles([1.10 + i * 0.001 for i in range(12)]),
            indicators(ema_20=1.12, ema_50=1.11, ema_200=1.10, adx_14=30),
        )
        self.assertGreaterEqual(result.score, 8)
        self.assertLessEqual(result.score, cfg.weights.trend)

    def test_no_alignment_scores_zero(self):
        engine = TrendEngine()
        result = engine.run(candles([1.10] * 5), indicators())
        self.assertEqual(result.score, 0)


if __name__ == "__main__":
    unittest.main()

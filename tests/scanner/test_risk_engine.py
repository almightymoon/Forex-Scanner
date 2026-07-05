import unittest

from services.scanner_service.risk_engine import RiskEngine
from shared.types.models import NewsContext, RiskLevel, SignalDirection, TrendDirection

from tests.helpers import candles, indicators


class TestRiskEngine(unittest.TestCase):
    def test_near_support_on_bullish_trend(self):
        engine = RiskEngine()
        cs = candles([1.10] * 19 + [1.1005])
        result = engine.analyze_support_resistance(cs, indicators(), TrendDirection.BULLISH)
        self.assertTrue(result.near_support)

    def test_high_risk_near_news(self):
        engine = RiskEngine()
        news = NewsContext(has_high_impact_soon=True, minutes_until_event=10)
        self.assertEqual(engine.assess_risk(90, news, True), RiskLevel.HIGH)

    def test_buy_levels_calculated(self):
        engine = RiskEngine()
        cs = candles([1.10] * 20)
        entry, sl, tp1, _, _, rr = engine.calculate_levels(
            cs, indicators(atr_14=0.002), SignalDirection.BUY
        )
        self.assertIsNotNone(entry)
        self.assertLess(sl, cs[-1].close)


if __name__ == "__main__":
    unittest.main()

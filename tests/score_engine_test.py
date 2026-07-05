import unittest

from services.scanner_service.models import MomentumAnalysis
from services.scanner_service.score_engine import ScoreEngine, MAX_MTF, MAX_NEWS
from shared.types.models import NewsContext, NewsImpact, SMCPattern, SignalDirection, TrendDirection


class TestScoreEngine(unittest.TestCase):
    def test_mtf_full_alignment(self):
        engine = ScoreEngine()
        trends = {tf: TrendDirection.BULLISH for tf in ("M15", "H1", "H4", "D1")}
        mtf = engine.analyze_mtf(trends, TrendDirection.BULLISH)
        self.assertTrue(mtf.aligned)
        self.assertEqual(mtf.score, MAX_MTF)

    def test_news_high_impact_soon_is_zero(self):
        engine = ScoreEngine()
        news = NewsContext(has_high_impact_soon=True, minutes_until_event=15)
        self.assertEqual(engine.score_news(news), 0)

    def test_news_clear_is_max(self):
        engine = ScoreEngine()
        self.assertEqual(engine.score_news(NewsContext(impact=NewsImpact.LOW)), MAX_NEWS)

    def test_breakdown_total(self):
        engine = ScoreEngine()
        bd = engine.build_breakdown(18, 24, 11, 5, 3, 10, 10)
        self.assertEqual(bd.total, 81)

    def test_direction_buy_on_bullish_trend(self):
        engine = ScoreEngine()
        smc = [SMCPattern(pattern_type="order_block", direction=SignalDirection.BUY, strength=0.9)]
        direction = engine.determine_direction(
            TrendDirection.BULLISH, smc, MomentumAnalysis(score=10)
        )
        self.assertEqual(direction, SignalDirection.BUY)


if __name__ == "__main__":
    unittest.main()

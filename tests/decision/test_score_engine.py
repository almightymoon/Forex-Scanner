import unittest

from services.scanner_service.models import MomentumAnalysis
from services.scanner_service.score_engine import ScoreEngine
from shared.config import get_scanner_config
from shared.types.models import NewsContext, NewsImpact, SMCPattern, SignalDirection, TrendDirection


class TestScoreEngine(unittest.TestCase):
    def test_mtf_full_alignment(self):
        cfg = get_scanner_config().scoring
        engine = ScoreEngine()
        trends = {tf: TrendDirection.BULLISH for tf in ("M15", "H1", "H4", "D1")}
        mtf = engine.analyze_mtf(trends, TrendDirection.BULLISH)
        self.assertTrue(mtf.aligned)
        self.assertEqual(mtf.score, cfg.mtf.max_points)

    def test_news_imminent_is_zero(self):
        engine = ScoreEngine()
        news = NewsContext(has_high_impact_soon=True, minutes_until_event=15)
        self.assertEqual(engine.score_news(news), 0)

    def test_breakdown_total(self):
        engine = ScoreEngine()
        bd = engine.build_breakdown(18, 24, 11, 5, 3, 10, 10)
        self.assertEqual(bd.total, 81)

    def test_direction_buy(self):
        engine = ScoreEngine()
        smc = [SMCPattern(pattern_type="bos", direction=SignalDirection.BUY)]
        direction = engine.determine_direction(
            TrendDirection.BULLISH, smc, MomentumAnalysis(score=10)
        )
        self.assertEqual(direction, SignalDirection.BUY)


if __name__ == "__main__":
    unittest.main()

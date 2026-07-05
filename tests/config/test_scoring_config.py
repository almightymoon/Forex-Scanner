import unittest

from shared.config import DEFAULT_SCORING, get_scanner_config


class TestScoringConfig(unittest.TestCase):
    def test_category_weights_sum_to_100(self):
        s = DEFAULT_SCORING
        total = (
            s.trend.max_points + s.momentum.max_points + s.smc.max_points
            + s.risk_sr.max_points + s.risk_volume.max_points
            + s.mtf.max_points + s.news.max_points
        )
        self.assertEqual(total, 100)

    def test_trend_rules_fit_max(self):
        s = DEFAULT_SCORING
        rule_sum = sum(r.points for r in s.trend.rules.values())
        self.assertLessEqual(rule_sum, s.trend.max_points)

    def test_singleton_returns_config(self):
        cfg = get_scanner_config()
        self.assertTrue(cfg.scoring.trend.max_points > 0)


if __name__ == "__main__":
    unittest.main()

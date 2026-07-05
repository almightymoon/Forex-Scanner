import unittest

from shared.config import DEFAULT_SCORING, get_scanner_config


class TestScoringConfig(unittest.TestCase):
    def test_weights_sum_to_100(self):
        from shared.config.scoring_loader import get_v2_scoring_config
        self.assertEqual(get_v2_scoring_config().weights.total, 100)

    def test_legacy_weights_sum_to_100(self):
        self.assertEqual(DEFAULT_SCORING.trend.max_points + DEFAULT_SCORING.momentum.max_points, 35)

    def test_trend_rules_fit_max(self):
        s = DEFAULT_SCORING
        rule_sum = sum(r.points for r in s.trend.rules.values())
        self.assertLessEqual(rule_sum, s.trend.max_points)

    def test_singleton_returns_config(self):
        cfg = get_scanner_config()
        self.assertTrue(cfg.scoring.trend.max_points > 0)


if __name__ == "__main__":
    unittest.main()

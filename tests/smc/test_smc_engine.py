import unittest

from services.scanner_service.smc_engine import SMCScoreEngine
from shared.config.scoring_loader import get_v2_scoring_config
from shared.types.models import SMCPattern, SignalDirection, TrendDirection


class TestSMCEngine(unittest.TestCase):
    """Legacy SMC score engine — kept for backward compatibility."""

    def test_order_block_weight(self):
        cfg = get_v2_scoring_config()
        engine = SMCScoreEngine()
        patterns = [SMCPattern(pattern_type="order_block", direction=SignalDirection.BUY)]
        score, _ = engine.analyze(patterns, TrendDirection.RANGING)
        self.assertGreater(score, 0)
        self.assertLessEqual(score, cfg.weights.order_block + cfg.weights.market_structure)


if __name__ == "__main__":
    unittest.main()

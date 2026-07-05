import unittest

from services.scanner_service.smc_engine import SMCScoreEngine
from shared.config import get_scanner_config
from shared.types.models import SMCPattern, SignalDirection, TrendDirection


class TestSMCEngine(unittest.TestCase):
    def test_order_block_weight_from_config(self):
        cfg = get_scanner_config().scoring
        engine = SMCScoreEngine()
        patterns = [SMCPattern(pattern_type="order_block", direction=SignalDirection.BUY)]
        score, _ = engine.analyze(patterns, TrendDirection.RANGING)
        self.assertEqual(score, cfg.smc.rules["order_block"].points)

    def test_aligned_patterns_get_boost(self):
        cfg = get_scanner_config().scoring
        engine = SMCScoreEngine()
        patterns = [
            SMCPattern(pattern_type="fvg", direction=SignalDirection.SELL),
            SMCPattern(pattern_type="liquidity_sweep", direction=SignalDirection.SELL),
        ]
        score, _ = engine.analyze(patterns, TrendDirection.BEARISH)
        base = cfg.smc.rules["fvg"].points + cfg.smc.rules["liquidity_sweep"].points
        boosted = int(cfg.smc.rules["fvg"].points * cfg.smc_trend_alignment_boost) + int(
            cfg.smc.rules["liquidity_sweep"].points * cfg.smc_trend_alignment_boost
        )
        self.assertEqual(score, boosted)
        self.assertGreater(boosted, base)

    def test_caps_at_max(self):
        cfg = get_scanner_config().scoring
        engine = SMCScoreEngine()
        patterns = [
            SMCPattern(pattern_type=t, direction=SignalDirection.BUY)
            for t in ("order_block", "fvg", "liquidity_sweep", "bos", "choch")
        ]
        score, _ = engine.analyze(patterns, TrendDirection.BULLISH)
        self.assertEqual(score, cfg.smc.max_points)


if __name__ == "__main__":
    unittest.main()

import unittest

from services.scanner_service.smc_engine import SMCScoreEngine, MAX_SMC, WEIGHTS
from shared.types.models import SMCPattern, SignalDirection, TrendDirection


class TestSMCEngine(unittest.TestCase):
    def test_order_block_scores_highest_weight(self):
        engine = SMCScoreEngine()
        patterns = [SMCPattern(pattern_type="order_block", direction=SignalDirection.BUY)]
        score, reasons = engine.analyze(patterns, TrendDirection.RANGING)
        self.assertEqual(score, WEIGHTS["order_block"])
        self.assertTrue(any("Order Block" in r for r in reasons))

    def test_multiple_patterns_cap_at_max(self):
        engine = SMCScoreEngine()
        patterns = [
            SMCPattern(pattern_type="order_block", direction=SignalDirection.BUY),
            SMCPattern(pattern_type="fvg", direction=SignalDirection.BUY),
            SMCPattern(pattern_type="liquidity_sweep", direction=SignalDirection.BUY),
            SMCPattern(pattern_type="bos", direction=SignalDirection.BUY),
            SMCPattern(pattern_type="choch", direction=SignalDirection.BUY),
        ]
        score, _ = engine.analyze(patterns, TrendDirection.BULLISH)
        self.assertEqual(score, MAX_SMC)

    def test_fvg_and_liquidity_contribute(self):
        engine = SMCScoreEngine()
        patterns = [
            SMCPattern(pattern_type="fvg", direction=SignalDirection.SELL),
            SMCPattern(pattern_type="liquidity_sweep", direction=SignalDirection.SELL),
        ]
        score, reasons = engine.analyze(patterns, TrendDirection.BEARISH)
        expected = int(WEIGHTS["fvg"] * 1.2) + int(WEIGHTS["liquidity_sweep"] * 1.2)
        self.assertEqual(score, expected)
        self.assertEqual(len(reasons), 2)


if __name__ == "__main__":
    unittest.main()

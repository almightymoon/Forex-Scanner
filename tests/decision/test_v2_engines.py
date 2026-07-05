"""Decision Engine V2 — unit tests for independent engines."""

import unittest
from datetime import datetime

from services.scanner_service.decision_engine import DecisionEngine
from services.scanner_service.fair_value_gap_engine import FairValueGapEngine
from services.scanner_service.liquidity_engine import LiquidityEngine
from services.scanner_service.market_structure_engine import MarketStructureEngine
from services.scanner_service.momentum_engine import MomentumEngine
from services.scanner_service.mtf_engine import MultiTimeframeEngine
from services.scanner_service.order_block_engine import OrderBlockEngine
from services.scanner_service.trend_engine import TrendEngine
from services.scanner_service.volatility_engine import VolatilityEngine
from shared.config.scoring_loader import get_v2_scoring_config
from shared.types.models import SMCPattern, SignalDirection, Timeframe, TrendDirection
from tests.helpers import candles, indicators


class TestV2Weights(unittest.TestCase):
    def test_weights_sum_to_100(self):
        self.assertEqual(get_v2_scoring_config().weights.total, 100)


class TestV2Engines(unittest.TestCase):
    def test_trend_engine_output_schema(self):
        out = TrendEngine().run(candles([1.10 + i * 0.001 for i in range(12)]), indicators(
            ema_20=1.12, ema_50=1.11, ema_200=1.10, adx_14=30
        ))
        self.assertEqual(out.name, "Trend")
        self.assertLessEqual(out.score, out.max_score)
        self.assertGreater(out.confidence, 0)

    def test_market_structure_from_patterns(self):
        patterns = [SMCPattern(pattern_type="bos", direction=SignalDirection.BUY, strength=70)]
        out = MarketStructureEngine().run(patterns, candles([1.10 + i * 0.001 for i in range(30)]))
        self.assertGreater(out.score, 0)
        self.assertEqual(out.direction, "BUY")

    def test_liquidity_engine(self):
        patterns = [SMCPattern(pattern_type="liquidity_sweep", direction=SignalDirection.BUY)]
        out = LiquidityEngine().run(patterns)
        self.assertGreater(out.score, 0)

    def test_order_block_engine(self):
        patterns = [SMCPattern(pattern_type="order_block", direction=SignalDirection.BUY, metadata={"index": 5})]
        out = OrderBlockEngine().run(patterns)
        self.assertGreater(out.score, 0)

    def test_fvg_engine(self):
        patterns = [SMCPattern(pattern_type="fvg", direction=SignalDirection.BUY, metadata={"gap_size": 0.001})]
        out = FairValueGapEngine().run(patterns)
        self.assertGreater(out.score, 0)

    def test_momentum_engine(self):
        out = MomentumEngine().run(60, indicators(macd_histogram=0.5, rsi_14=60, atr_14=0.002))
        self.assertLessEqual(out.score, out.max_score)

    def test_volatility_engine(self):
        out = VolatilityEngine().run(candles([1.10] * 20), indicators(atr_14=0.002))
        self.assertEqual(out.name, "Volatility")

    def test_mtf_engine_alignment(self):
        trends = {"M15": TrendDirection.BULLISH, "H1": TrendDirection.BULLISH, "H4": TrendDirection.BULLISH}
        out = MultiTimeframeEngine().run(trends, TrendDirection.BULLISH)
        self.assertEqual(out.score, out.max_score)


class TestDecisionEngineV2(unittest.TestCase):
    def test_full_evaluation_deterministic(self):
        engine = DecisionEngine()
        cs = candles([1.10 + i * 0.001 for i in range(60)])
        ind = indicators(
            ema_20=1.12, ema_50=1.11, ema_200=1.10, adx_14=30,
            macd_histogram=0.5, rsi_14=60, atr_14=0.002,
            bb_lower=1.09, bb_middle=1.105, bb_upper=1.12,
        )
        patterns = [
            SMCPattern(pattern_type="bos", direction=SignalDirection.BUY),
            SMCPattern(pattern_type="order_block", direction=SignalDirection.BUY),
        ]
        s1 = engine.evaluate("EURUSD", Timeframe.H1, cs, ind, patterns, {"H1": TrendDirection.BULLISH})
        s2 = engine.evaluate("EURUSD", Timeframe.H1, cs, ind, patterns, {"H1": TrendDirection.BULLISH})
        self.assertEqual(s1.score, s2.score)
        self.assertEqual(len(s1.engine_outputs), 10)
        self.assertIsNotNone(s1.score_breakdown_v2)
        self.assertGreater(s1.confidence, 0)

    def test_engine_outputs_serializable(self):
        engine = DecisionEngine()
        signal = engine.evaluate(
            "EURUSD", Timeframe.H1, candles([1.10] * 60),
            indicators(ema_20=1.11, ema_50=1.10, rsi_14=55),
            [],
        )
        for out in signal.engine_outputs:
            self.assertIn("name", out)
            self.assertIn("score", out)
            self.assertIn("max_score", out)


if __name__ == "__main__":
    unittest.main()

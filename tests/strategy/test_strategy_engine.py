import unittest

from services.strategy_engine import Combinator, RuleOperator, Strategy, StrategyEvaluator, StrategyRule
from shared.types.models import IndicatorValues, SMCPattern, SignalDirection, Timeframe
from datetime import datetime


class TestStrategyEngine(unittest.TestCase):
    def test_ema_and_rsi_rules(self):
        strategy = Strategy(
            id="test",
            name="EMA + RSI",
            rules=[
                StrategyRule("ema20.ema50", RuleOperator.CROSS_ABOVE, label="EMA20 > EMA50"),
                StrategyRule("rsi", RuleOperator.GT, 60, label="RSI > 60"),
            ],
            combinator=Combinator.AND,
        )
        indicators = IndicatorValues(
            symbol="EURUSD", timeframe=Timeframe.H1, timestamp=datetime(2025, 1, 1),
            ema_20=1.12, ema_50=1.10, rsi_14=65,
        )
        matched, reasons = StrategyEvaluator().evaluate(strategy, indicators, [])
        self.assertTrue(matched)
        self.assertEqual(len(reasons), 2)

    def test_smc_bos_rule(self):
        strategy = Strategy(
            id="smc",
            name="BOS",
            rules=[StrategyRule("smc.bos", RuleOperator.PRESENT, "buy")],
        )
        patterns = [SMCPattern(pattern_type="bos", direction=SignalDirection.BUY)]
        matched, _ = StrategyEvaluator().evaluate(
            strategy,
            IndicatorValues(symbol="EURUSD", timeframe=Timeframe.H1, timestamp=datetime(2025, 1, 1)),
            patterns,
        )
        self.assertTrue(matched)


if __name__ == "__main__":
    unittest.main()

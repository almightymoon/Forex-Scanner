import unittest
from datetime import datetime, timezone

from services.market_data_service.candle_builder import generate_candles, update_last_candle
from services.market_data_service.tick_processor import TickProcessor
from services.market_data_service.validator import DataValidator
from shared.types.models import Candle, Tick, Timeframe


class TestMarketData(unittest.TestCase):
    def test_validator_rejects_bad_candle(self):
        v = DataValidator()
        bad = Candle(
            symbol="EURUSD", timeframe=Timeframe.H1,
            timestamp=datetime.now(timezone.utc),
            open=1.1, high=1.0, low=1.2, close=1.1,
        )
        self.assertFalse(v.validate_candle(bad))

    def test_candle_builder_anchors(self):
        cs = generate_candles("EURUSD", Timeframe.H1, 10, 1.10, anchor_price=1.15)
        self.assertEqual(cs[-1].close, 1.15)

    def test_tick_processor_new_bar(self):
        proc = TickProcessor(Timeframe.M1)
        ts = datetime(2025, 6, 1, 10, 0, tzinfo=timezone.utc)
        proc.process_tick(Tick(symbol="EURUSD", timestamp=ts, bid=1.1, ask=1.1002))
        completed = proc.process_tick(
            Tick(symbol="EURUSD", timestamp=ts.replace(minute=1), bid=1.101, ask=1.1012)
        )
        self.assertIsNotNone(completed)


if __name__ == "__main__":
    unittest.main()

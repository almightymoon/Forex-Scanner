import unittest
from datetime import datetime, timezone

from services.market_data_service.candle_builder import generate_candles, update_last_candle
from services.market_data_service.tick_processor import TickProcessor
from services.market_data_service.validator import DataValidator
from shared.types.models import Candle, Tick, Timeframe


class TestMarketDataValidator(unittest.TestCase):
    def test_rejects_invalid_candle(self):
        v = DataValidator()
        bad = Candle(
            symbol="EURUSD", timeframe=Timeframe.H1,
            timestamp=datetime.now(timezone.utc),
            open=1.1, high=1.0, low=1.2, close=1.1,
        )
        self.assertFalse(v.validate_candle(bad))

    def test_accepts_valid_candle(self):
        v = DataValidator()
        good = Candle(
            symbol="EURUSD", timeframe=Timeframe.H1,
            timestamp=datetime.now(timezone.utc),
            open=1.1, high=1.12, low=1.09, close=1.11,
        )
        self.assertTrue(v.validate_candle(good))

    def test_rejects_inverted_tick(self):
        v = DataValidator()
        tick = Tick(symbol="EURUSD", timestamp=datetime.now(timezone.utc), bid=1.1, ask=1.09)
        self.assertFalse(v.validate_tick(tick))


class TestCandleBuilder(unittest.TestCase):
    def test_generate_anchors_last_bar(self):
        cs = generate_candles("EURUSD", Timeframe.H1, 10, 1.10, anchor_price=1.15)
        self.assertEqual(cs[-1].close, 1.15)

    def test_update_last_candle(self):
        c = Candle(
            symbol="EURUSD", timeframe=Timeframe.H1,
            timestamp=datetime.now(timezone.utc),
            open=1.1, high=1.11, low=1.09, close=1.1,
        )
        updated = update_last_candle(c, 1.12)
        self.assertEqual(updated.close, 1.12)
        self.assertGreaterEqual(updated.high, 1.12)


class TestTickProcessor(unittest.TestCase):
    def test_builds_candle_from_ticks(self):
        proc = TickProcessor(Timeframe.M1)
        ts = datetime(2025, 6, 1, 10, 0, tzinfo=timezone.utc)
        proc.process_tick(Tick(symbol="EURUSD", timestamp=ts, bid=1.1, ask=1.1002))
        completed = proc.process_tick(
            Tick(symbol="EURUSD", timestamp=ts.replace(minute=1), bid=1.101, ask=1.1012)
        )
        self.assertIsNotNone(completed)
        self.assertEqual(completed.symbol, "EURUSD")


if __name__ == "__main__":
    unittest.main()

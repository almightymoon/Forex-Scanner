"""Unit tests for data normalization."""

import unittest
from datetime import datetime, timezone

from services.data_collector.models import RawCandle
from services.data_collector.normalizer import DataNormalizer
from shared.types.models import Timeframe


class TestNormalizer(unittest.TestCase):
    def setUp(self):
        self.normalizer = DataNormalizer("mock")

    def test_normalize_candle(self):
        raw = RawCandle(
            symbol="eur/usd",
            timeframe="H1",
            timestamp=datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
            open=1.1,
            high=1.105,
            low=1.095,
            close=1.102,
            volume=1000,
        )
        candle = self.normalizer.normalize_candle(raw)
        self.assertEqual(candle.symbol, "EURUSD")
        self.assertEqual(candle.timeframe, Timeframe.H1)
        self.assertEqual(candle.provider, "mock")
        self.assertEqual(candle.open, 1.1)
        self.assertIsNotNone(candle.created_at)

    def test_naive_timestamp_gets_utc(self):
        raw = RawCandle("EURUSD", "M5", datetime(2024, 6, 1, 10, 0), 1.0, 1.1, 0.9, 1.05)
        candle = self.normalizer.normalize_candle(raw)
        self.assertEqual(candle.timestamp.tzinfo, timezone.utc)

    def test_invalid_timeframe_raises(self):
        raw = RawCandle("EURUSD", "INVALID", datetime.now(timezone.utc), 1, 1, 1, 1)
        with self.assertRaises(ValueError):
            self.normalizer.normalize_candle(raw)

    def test_expected_interval_seconds(self):
        self.assertEqual(DataNormalizer.expected_interval_seconds(Timeframe.H1), 3600)
        self.assertEqual(DataNormalizer.expected_interval_seconds(Timeframe.M1), 60)


if __name__ == "__main__":
    unittest.main()

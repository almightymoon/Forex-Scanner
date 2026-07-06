"""Tests for expanded validation rules."""

import unittest
from datetime import datetime, timedelta, timezone

from services.data_collector.config import ValidationConfig
from services.data_collector.models import CollectedCandle
from services.data_collector.validator import DataValidator
from shared.types.models import Timeframe


class TestExpandedValidation(unittest.TestCase):
    def setUp(self):
        self.validator = DataValidator(ValidationConfig(
            max_spread_ratio=0.05,
            max_price_spike_ratio=0.05,
        ))

    def test_price_spike_rejected(self):
        t1 = datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc)
        t2 = datetime(2024, 1, 1, 11, 0, tzinfo=timezone.utc)
        c1 = CollectedCandle("EURUSD", Timeframe.H1, t1, 1.0, 1.01, 0.99, 1.0, 100, "m", datetime.now(timezone.utc))
        c2 = CollectedCandle("EURUSD", Timeframe.H1, t2, 1.2, 1.25, 1.15, 1.22, 100, "m", datetime.now(timezone.utc))
        result = self.validator.validate_candles([c1, c2])
        self.assertEqual(len(result.valid), 1)
        self.assertEqual(len(result.rejected), 1)

    def test_invalid_spread_rejected(self):
        ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
        c = CollectedCandle("EURUSD", Timeframe.H1, ts, 1.0, 1.5, 0.5, 1.0, 100, "m", datetime.now(timezone.utc))
        ok, reason = self.validator.validate_candle(c)
        self.assertFalse(ok)
        self.assertEqual(reason, "invalid spread")

    def test_high_below_open_rejected(self):
        ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
        c = CollectedCandle("EURUSD", Timeframe.H1, ts, 1.1, 1.05, 1.0, 1.08, 100, "m", datetime.now(timezone.utc))
        ok, reason = self.validator.validate_candle(c)
        self.assertFalse(ok)
        self.assertEqual(reason, "high < open")


if __name__ == "__main__":
    unittest.main()

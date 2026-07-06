"""Unit tests for data validation."""

import unittest
from datetime import datetime, timedelta, timezone

from services.data_collector.models import CollectedCandle, CollectedTick
from services.data_collector.validator import DataValidator
from services.data_collector.config import ValidationConfig
from shared.types.models import Timeframe


def _candle(
    ts: datetime,
    o: float = 1.1,
    h: float = 1.15,
    l: float = 1.05,
    c: float = 1.12,
) -> CollectedCandle:
    return CollectedCandle(
        symbol="EURUSD",
        timeframe=Timeframe.H1,
        timestamp=ts,
        open=o,
        high=h,
        low=l,
        close=c,
        volume=100,
        provider="mock",
        created_at=datetime.now(timezone.utc),
    )


class TestValidator(unittest.TestCase):
    def setUp(self):
        self.validator = DataValidator(ValidationConfig())

    def test_valid_candle_passes(self):
        ok, reason = self.validator.validate_candle(
            _candle(datetime(2024, 1, 1, tzinfo=timezone.utc))
        )
        self.assertTrue(ok)
        self.assertIsNone(reason)

    def test_high_below_low_rejected(self):
        ok, reason = self.validator.validate_candle(
            _candle(datetime(2024, 1, 1, tzinfo=timezone.utc), h=1.0, l=1.2)
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "high < low")

    def test_negative_price_rejected(self):
        ok, _ = self.validator.validate_candle(
            _candle(datetime(2024, 1, 1, tzinfo=timezone.utc), o=-1)
        )
        self.assertFalse(ok)

    def test_future_timestamp_rejected(self):
        future = datetime.now(timezone.utc) + timedelta(hours=2)
        ok, reason = self.validator.validate_candle(_candle(future))
        self.assertFalse(ok)
        self.assertEqual(reason, "future timestamp")

    def test_duplicate_timestamps_rejected(self):
        ts = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
        result = self.validator.validate_candles([_candle(ts), _candle(ts)])
        self.assertEqual(len(result.valid), 1)
        self.assertEqual(len(result.rejected), 1)

    def test_gap_detection(self):
        t1 = datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc)
        t2 = datetime(2024, 1, 1, 14, 0, tzinfo=timezone.utc)
        result = self.validator.validate_candles([_candle(t1), _candle(t2)])
        self.assertEqual(len(result.valid), 2)
        self.assertEqual(len(result.gaps_detected), 1)
        self.assertTrue(any("gap detected" in w for w in result.warnings))

    def test_tick_ask_below_bid_rejected(self):
        tick = CollectedTick(
            "EURUSD", datetime.now(timezone.utc), 1.1, 1.09, 0, "mock",
            datetime.now(timezone.utc),
        )
        ok, reason = self.validator.validate_tick(tick)
        self.assertFalse(ok)
        self.assertEqual(reason, "ask < bid")


if __name__ == "__main__":
    unittest.main()

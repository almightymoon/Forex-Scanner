"""Tests for gap detection engine."""

import unittest
from datetime import datetime, timedelta, timezone

from services.data_collector.gap_detection import GapDetectionEngine
from services.data_collector.models import CollectedCandle, GapType
from shared.types.models import Timeframe


def _c(ts_hour: int) -> CollectedCandle:
    ts = datetime(2024, 1, 1, ts_hour, 0, tzinfo=timezone.utc)
    return CollectedCandle(
        "EURUSD", Timeframe.H1, ts, 1.1, 1.12, 1.09, 1.11, 100, "mock",
        datetime.now(timezone.utc),
    )


class TestGapDetection(unittest.TestCase):
    def setUp(self):
        self.engine = GapDetectionEngine()

    def test_detects_missing_candle(self):
        candles = [_c(10), _c(11), _c(13)]
        report = self.engine.detect(candles, "EURUSD", Timeframe.H1)
        missing = [g for g in report.gaps if g.gap_type == GapType.MISSING]
        self.assertGreater(len(missing), 0)
        self.assertEqual(report.missing, 1)

    def test_detects_duplicate(self):
        ts = datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc)
        c = _c(10)
        report = self.engine.detect([c, c], "EURUSD", Timeframe.H1)
        self.assertEqual(report.duplicates, 1)
        self.assertTrue(any(g.gap_type == GapType.DUPLICATE for g in report.gaps))

    def test_detects_out_of_order(self):
        candles = [_c(12), _c(10), _c(11)]
        report = self.engine.detect(candles, "EURUSD", Timeframe.H1)
        self.assertGreater(report.out_of_order, 0)

    def test_detect_missing_in_range(self):
        existing = {
            datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
            datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
        }
        start = datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc)
        end = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
        report = self.engine.detect_missing_in_range(
            existing, "EURUSD", Timeframe.H1, start, end,
        )
        self.assertEqual(report.missing, 1)


if __name__ == "__main__":
    unittest.main()

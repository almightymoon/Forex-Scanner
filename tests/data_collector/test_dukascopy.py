"""Tests for Dukascopy bi5 parsing."""

import unittest
from datetime import datetime, timezone

from services.data_collector.providers.dukascopy.bi5 import ticks_to_candles


class TestDukascopyBi5(unittest.TestCase):
    def test_ticks_to_candles(self):
        base = datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc)
        ticks = [
            (base, 1.1000, 1.1002, 1.0),
            (base.replace(minute=0, second=30), 1.1005, 1.1007, 2.0),
            (base.replace(minute=1), 1.0990, 1.0992, 1.5),
        ]
        candles = ticks_to_candles(ticks, interval_seconds=60)
        self.assertGreaterEqual(len(candles), 1)
        self.assertAlmostEqual(candles[0]["open"], 1.1001, places=4)


if __name__ == "__main__":
    unittest.main()

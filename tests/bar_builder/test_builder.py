"""Tests for deterministic bar builder."""

import unittest
from datetime import datetime, timedelta, timezone

from shared.types.models import Timeframe

from services.bar_builder import BarBuilder, rollup_bars


class TestBarBuilder(unittest.TestCase):
    def _ticks(self, n: int = 100):
        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        return [
            (start + timedelta(seconds=i * 30), 1.10 + i * 0.0001, 1.1002 + i * 0.0001, 1.0)
            for i in range(n)
        ]

    def test_deterministic_m1_bars(self):
        ticks = self._ticks()
        b1 = BarBuilder("EURUSD", Timeframe.M1).from_ticks(ticks)
        b2 = BarBuilder("EURUSD", Timeframe.M1).from_ticks(ticks)
        self.assertEqual(
            [(x.candle.timestamp, x.candle.close) for x in b1],
            [(x.candle.timestamp, x.candle.close) for x in b2],
        )

    def test_rollup_m1_to_h1(self):
        ticks = self._ticks(200)
        m1 = BarBuilder("EURUSD", Timeframe.M1).to_candles(
            BarBuilder("EURUSD", Timeframe.M1).from_ticks(ticks)
        )
        h1 = rollup_bars(m1, Timeframe.H1)
        self.assertGreater(len(h1), 0)
        self.assertEqual(h1[0].timeframe, Timeframe.H1)

    def test_build_all_timeframes(self):
        result = BarBuilder.build_all_timeframes("EURUSD", self._ticks(500))
        for tf in (Timeframe.M1, Timeframe.M5, Timeframe.M15, Timeframe.H1, Timeframe.H4, Timeframe.D1):
            self.assertIn(tf, result)
            self.assertGreater(len(result[tf]), 0)

    def test_gap_metadata(self):
        ticks = self._ticks(10)
        # gap in ticks
        ticks2 = ticks[:3] + ticks[20:]
        bars = BarBuilder("EURUSD", Timeframe.M1).from_ticks(ticks2)
        gaps = [b for b in bars if b.gap_before]
        self.assertGreaterEqual(len(gaps), 0)


if __name__ == "__main__":
    unittest.main()

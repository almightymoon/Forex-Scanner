"""Tests for swing analysis and historical setup matching."""

import unittest

from services.scanner_service.swing_analysis import (
    analyze_trend_context,
    build_zigzag_swings,
    classify_bos,
    detect_session_liquidity,
    find_swings,
    session_from_hour,
)
from services.setup_intelligence import HistoricalSetupAnalyzer, SetupFingerprint
from shared.types.models import SignalDirection, Timeframe, TrendDirection
from tests.helpers import candles


class TestSwingAnalysis(unittest.TestCase):
    def test_find_swings_on_uptrend(self):
        prices = [1.10 + (i % 6) * 0.003 + i * 0.0003 for i in range(40)]
        cs = candles(prices)
        highs, lows = find_swings(cs)
        swings = build_zigzag_swings(cs)
        self.assertGreaterEqual(len(swings), len(highs) + len(lows) - 2)

    def test_trend_context_bullish(self):
        prices = [1.10 + i * 0.002 for i in range(40)]
        ctx = analyze_trend_context(candles(prices), ema20=1.15, ema50=1.12)
        self.assertIn(ctx.direction, (TrendDirection.BULLISH, TrendDirection.RANGING))

    def test_session_from_hour(self):
        self.assertEqual(session_from_hour(3), "asia")
        self.assertEqual(session_from_hour(10), "london")

    def test_classify_bos(self):
        from services.scanner_service.swing_analysis import SwingPoint

        highs = [SwingPoint(10, 1.12, "high"), SwingPoint(20, 1.14, "high")]
        lows = [SwingPoint(5, 1.08, "low"), SwingPoint(15, 1.10, "low")]
        kind = classify_bos(highs, lows, 1.135)
        self.assertIn(kind, ("internal", "external"))


class TestHistoricalMatcher(unittest.TestCase):
    def test_fingerprint_similarity(self):
        a = SetupFingerprint("buy", "bullish", frozenset({"bos", "order_block"}), 8)
        b = SetupFingerprint("buy", "bullish", frozenset({"bos", "fvg"}), 7)
        self.assertGreater(a.similarity(b), 0.3)

    def test_fingerprint_mismatch_direction(self):
        a = SetupFingerprint("buy", "bullish", frozenset({"bos"}), 8)
        b = SetupFingerprint("sell", "bearish", frozenset({"bos"}), 8)
        self.assertEqual(a.similarity(b), 0.0)

    def test_historical_analyzer_returns_evidence(self):
        prices = [1.10 + (i % 5) * 0.001 + i * 0.0005 for i in range(120)]
        cs = candles(prices)
        fp = SetupFingerprint("buy", "bullish", frozenset({"bos"}), 7)
        evidence = HistoricalSetupAnalyzer().analyze("EURUSD", Timeframe.H1, cs, fp)
        self.assertIsNotNone(evidence.to_dict())
        self.assertIn("sample_size", evidence.to_dict())


if __name__ == "__main__":
    unittest.main()

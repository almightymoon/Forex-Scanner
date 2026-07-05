"""Tests for structure scoring, historical confidence, and validation engine."""

import tempfile
import unittest
from pathlib import Path

from services.scanner_service.structure_scoring import score_structure_event
from services.setup_intelligence.historical_matcher import HistoricalEvidence, historical_confidence_multiplier
from services.validation_engine import OutcomeStore, SignalValidator, TrackedSignal
from shared.types.models import SMCPattern, SignalDirection, Timeframe
from tests.helpers import candles


class TestStructureScoring(unittest.TestCase):
    def test_bos_quality_bounded(self):
        cs = candles([1.10 + (i % 6) * 0.002 + i * 0.0002 for i in range(40)])
        p = SMCPattern(
            pattern_type="bos",
            direction=SignalDirection.BUY,
            strength=80,
            price_high=1.12,
            metadata={"swing_index": 30, "swing_strength": 82},
        )
        q = score_structure_event(p, cs)
        self.assertGreaterEqual(q.overall, 0)
        self.assertLessEqual(q.overall, 100)
        self.assertIn("stars", q.to_dict())


class TestHistoricalConfidence(unittest.TestCase):
    def test_boost_on_high_win_rate(self):
        ev = HistoricalEvidence(sample_size=50, win_rate=74)
        mult, msg = historical_confidence_multiplier(ev)
        self.assertGreater(mult, 1.0)
        self.assertIsNotNone(msg)

    def test_no_adjustment_small_sample(self):
        ev = HistoricalEvidence(sample_size=5, win_rate=80)
        mult, msg = historical_confidence_multiplier(ev)
        self.assertEqual(mult, 1.0)
        self.assertIsNone(msg)

    def test_reduce_on_low_win_rate(self):
        ev = HistoricalEvidence(sample_size=30, win_rate=38)
        mult, _ = historical_confidence_multiplier(ev)
        self.assertLess(mult, 1.0)


class TestValidationEngine(unittest.TestCase):
    def test_register_and_close_win(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = OutcomeStore(path=str(Path(tmp) / "outcomes.json"))
            validator = SignalValidator(store=store)

            sig = TrackedSignal(
                id="test1",
                symbol="EURUSD",
                timeframe="H1",
                direction="buy",
                score=85,
                confidence=0.82,
                entry_price=1.1000,
                stop_loss=1.0980,
                take_profit=1.1040,
            )
            store.save(sig)

            outcome_candles = candles([1.1005, 1.1020, 1.1050])
            closed = validator.evaluate_open_signals("EURUSD", outcome_candles)
            self.assertEqual(len(closed), 1)
            self.assertEqual(closed[0].outcome, "win")

            report = validator.report("EURUSD")
            self.assertEqual(report.metrics.wins, 1)
            self.assertEqual(report.metrics.win_rate, 100.0)


if __name__ == "__main__":
    unittest.main()

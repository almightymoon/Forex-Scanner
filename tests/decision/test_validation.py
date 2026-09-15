"""Tests for structure scoring, historical confidence, and validation engine."""

import tempfile
import unittest
from pathlib import Path

from services.scanner_service.structure_scoring import score_structure_event
from services.setup_intelligence.historical_matcher import HistoricalEvidence, historical_confidence_multiplier
from services.validation_engine import OutcomeStore, SignalValidator, TrackedSignal, get_outcome_store
from services.validation_engine.storage import DbOutcomeStore
from shared.database import Database
from shared.types.models import SMCPattern, SignalDirection
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

    def test_file_store_atomic_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "outcomes.json")
            store = OutcomeStore(path=path)
            store.save(
                TrackedSignal(
                    id="abc123",
                    symbol="XAUUSD",
                    timeframe="H1",
                    direction="sell",
                    score=72,
                    confidence=0.7,
                    entry_price=2400.0,
                    stop_loss=2405.0,
                    take_profit=2390.0,
                )
            )
            reloaded = OutcomeStore(path=path)
            got = reloaded.get("abc123")
            self.assertIsNotNone(got)
            self.assertEqual(got.symbol, "XAUUSD")

    def test_sqlite_outcome_store_idempotent_upsert(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(db_path=Path(tmp) / "test.db")
            store = DbOutcomeStore(db)
            sig = TrackedSignal(
                id="idempotent1",
                symbol="GBPUSD",
                timeframe="H1",
                direction="buy",
                score=80,
                confidence=0.8,
                entry_price=1.25,
                stop_loss=1.24,
                take_profit=1.27,
            )
            store.save(sig)
            sig.score = 88
            store.update(sig)
            rows = store.list_all(symbol="GBPUSD")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].score, 88)
            self.assertEqual(store.get("idempotent1").score, 88)

            validator = SignalValidator(store=store)
            closed = validator.evaluate_open_signals(
                "GBPUSD",
                candles([1.251, 1.26, 1.275]),
            )
            self.assertEqual(len(closed), 1)
            self.assertEqual(closed[0].outcome, "win")

    def test_get_outcome_store_explicit_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "explicit.json")
            store = get_outcome_store(path=path)
            self.assertIsInstance(store, OutcomeStore)


if __name__ == "__main__":
    unittest.main()

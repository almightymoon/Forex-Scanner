"""Unit tests for collector database layer."""

import os
import tempfile
import unittest
from datetime import datetime, timezone

from services.data_collector.database import CollectorDatabase, reset_collector_database
from services.data_collector.models import (
    CollectedCandle,
    CollectionLogEntry,
    ProviderHealthStatus,
    ProviderState,
)
from services.data_collector.symbols import SymbolRegistry
from shared.types.models import Timeframe


class TestCollectorDatabase(unittest.TestCase):
    def setUp(self):
        reset_collector_database()
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        os.environ["COLLECTOR_SQLITE_PATH"] = self.tmp.name
        self.db = CollectorDatabase(force_sqlite=True)

    def tearDown(self):
        reset_collector_database()
        os.unlink(self.tmp.name)
        os.environ.pop("COLLECTOR_SQLITE_PATH", None)

    def test_sync_symbols(self):
        count = self.db.sync_symbols(SymbolRegistry(("EURUSD", "XAUUSD")))
        self.assertEqual(count, 2)

    def test_insert_and_read_candles(self):
        ts = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
        candle = CollectedCandle(
            "EURUSD", Timeframe.H1, ts, 1.1, 1.15, 1.05, 1.12, 500, "mock",
            datetime.now(timezone.utc),
        )
        inserted = self.db.insert_candles([candle])
        self.assertEqual(inserted, 1)

        rows = self.db.get_candles("EURUSD", Timeframe.H1, limit=10)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].close, 1.12)
        self.assertEqual(rows[0].provider, "mock")

    def test_upsert_candle_updates(self):
        ts = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
        c1 = CollectedCandle(
            "EURUSD", Timeframe.H1, ts, 1.1, 1.15, 1.05, 1.12, 500, "mock",
            datetime.now(timezone.utc),
        )
        c2 = CollectedCandle(
            "EURUSD", Timeframe.H1, ts, 1.1, 1.16, 1.04, 1.14, 600, "mt5",
            datetime.now(timezone.utc),
        )
        self.db.insert_candles([c1])
        self.db.insert_candles([c2])
        rows = self.db.get_candles("EURUSD", Timeframe.H1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].close, 1.14)
        self.assertEqual(rows[0].provider, "mt5")

    def test_provider_status_roundtrip(self):
        status = ProviderHealthStatus(
            provider="mock",
            state=ProviderState.CONNECTED,
            connected=True,
            last_update=datetime.now(timezone.utc),
            rows_collected=100,
            rows_rejected=5,
            latency_ms=42.5,
            message="ok",
        )
        self.db.update_provider_status(status)
        loaded = self.db.get_provider_status("mock")
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded.rows_collected, 100)
        self.assertEqual(loaded.state, ProviderState.CONNECTED)

    def test_collection_log(self):
        log_id = self.db.log_collection(CollectionLogEntry(
            provider="mock",
            symbol="EURUSD",
            timeframe="H1",
            job_type="incremental_update",
            duration_ms=123.4,
            rows_imported=50,
            rows_rejected=2,
            status="completed",
        ))
        self.assertGreater(log_id, 0)

    def test_latest_timestamp(self):
        ts1 = datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc)
        ts2 = datetime(2024, 1, 1, 11, 0, tzinfo=timezone.utc)
        self.db.insert_candles([
            CollectedCandle("EURUSD", Timeframe.H1, ts1, 1, 1, 1, 1, 0, "mock", datetime.now(timezone.utc)),
            CollectedCandle("EURUSD", Timeframe.H1, ts2, 1, 1, 1, 1, 0, "mock", datetime.now(timezone.utc)),
        ])
        latest = self.db.get_latest_timestamp("EURUSD", Timeframe.H1)
        self.assertEqual(latest, ts2)


if __name__ == "__main__":
    unittest.main()

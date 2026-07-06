"""Tests for historical import manager."""

import asyncio
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from services.data_collector.database import CollectorDatabase, reset_collector_database
from services.data_collector.import_history import HistoricalImportManager
from services.data_collector.models import CollectedCandle, HistoricalRange, RawCandle
from tests.data_collector.mock_provider import MockDataProvider
from shared.types.models import Timeframe


class TestHistoricalImport(unittest.TestCase):
    def setUp(self):
        reset_collector_database()
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        os.environ["COLLECTOR_SQLITE_PATH"] = self.tmp.name
        self.db = CollectorDatabase(force_sqlite=True)

        now = datetime.now(timezone.utc)
        self.candles = [
            RawCandle("EURUSD", "H1", now - timedelta(hours=2), 1.1, 1.12, 1.09, 1.11, 100),
            RawCandle("EURUSD", "H1", now - timedelta(hours=1), 1.11, 1.13, 1.10, 1.12, 100),
        ]
        self.provider = MockDataProvider(self.candles)
        self.manager = HistoricalImportManager(self.db)

    def tearDown(self):
        reset_collector_database()
        os.unlink(self.tmp.name)
        os.environ.pop("COLLECTOR_SQLITE_PATH", None)

    def test_import_skips_existing(self):
        existing_ts = self.candles[0].timestamp
        self.db.insert_candles_batch([
            CollectedCandle("EURUSD", Timeframe.H1, existing_ts, 1, 1, 1, 1, 0, "mock",
                            datetime.now(timezone.utc)),
        ])

        async def run():
            await self.provider.connect()
            return await self.manager.import_range(
                self.provider, "EURUSD", Timeframe.H1, HistoricalRange.ONE_MONTH,
            )

        result = asyncio.run(run())
        self.assertEqual(result.rows_imported, 1)
        self.assertEqual(result.rows_skipped, 1)

    def test_batch_insert_transactional(self):
        candles = [
            CollectedCandle("EURUSD", Timeframe.H1,
                            datetime(2024, 1, 1, i, 0, tzinfo=timezone.utc),
                            1, 1, 1, 1, 0, "mock", datetime.now(timezone.utc))
            for i in range(5)
        ]
        with self.db.transaction():
            inserted = self.db.insert_candles_batch(candles, skip_existing=True)
        self.assertEqual(inserted, 5)
        self.assertEqual(self.db.count_candles(), 5)


if __name__ == "__main__":
    unittest.main()

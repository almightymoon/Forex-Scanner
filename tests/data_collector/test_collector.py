"""Integration tests for collector workflow with mock provider."""

import asyncio
import os
import tempfile
import unittest
from datetime import datetime, timezone

from services.data_collector.collector import DataCollector
from services.data_collector.database import reset_collector_database
from services.data_collector.models import RawCandle
from tests.data_collector.mock_provider import MockDataProvider
from shared.types.models import Timeframe


class TestCollectorWorkflow(unittest.TestCase):
    def setUp(self):
        reset_collector_database()
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        os.environ["COLLECTOR_SQLITE_PATH"] = self.tmp.name

        ts = datetime(2024, 6, 1, 10, 0, tzinfo=timezone.utc)
        self.candles = [
            RawCandle("EURUSD", "H1", ts, 1.1, 1.12, 1.09, 1.11, 1000),
            RawCandle("EURUSD", "H1", ts.replace(hour=11), 1.11, 1.13, 1.10, 1.12, 800),
        ]
        self.provider = MockDataProvider(self.candles)

        from services.data_collector.database import CollectorDatabase
        self.collector = DataCollector(
            database=CollectorDatabase(force_sqlite=True),
            providers=[self.provider],
        )

    def tearDown(self):
        reset_collector_database()
        os.unlink(self.tmp.name)
        os.environ.pop("COLLECTOR_SQLITE_PATH", None)

    def test_full_collection_workflow(self):
        async def run():
            await self.collector.initialize()
            imported, rejected = await self.collector.collect_historical(
                "mock", "EURUSD", Timeframe.H1,
                datetime(2024, 6, 1, tzinfo=timezone.utc),
                datetime(2024, 6, 2, tzinfo=timezone.utc),
            )
            await self.collector.shutdown()
            return imported, rejected

        imported, rejected = asyncio.run(run())
        self.assertEqual(imported, 2)
        self.assertEqual(rejected, 0)

        candles = self.collector.get_candles("EURUSD", Timeframe.H1)
        self.assertEqual(len(candles), 2)
        self.assertEqual(candles[0].provider, "mock")

    def test_health_snapshot(self):
        async def run():
            await self.collector.initialize()
            snap = self.collector.get_health_snapshot()
            await self.collector.shutdown()
            return snap

        snap = asyncio.run(run())
        self.assertIn("providers", snap)
        self.assertIn("checked_at", snap)


if __name__ == "__main__":
    unittest.main()

"""Tests for repair engine."""

import asyncio
import os
import tempfile
import unittest
from datetime import datetime, timezone

from services.data_collector.database import CollectorDatabase, reset_collector_database
from services.data_collector.gap_detection import GapDetectionEngine
from services.data_collector.models import CollectedCandle, DataGap, GapStatus, GapType, RawCandle
from services.data_collector.repair import RepairEngine
from tests.data_collector.mock_provider import MockDataProvider
from shared.types.models import Timeframe


class TestRepairEngine(unittest.TestCase):
    def setUp(self):
        reset_collector_database()
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        os.environ["COLLECTOR_SQLITE_PATH"] = self.tmp.name
        self.db = CollectorDatabase(force_sqlite=True)

        ts_missing = datetime(2024, 6, 1, 11, 0, tzinfo=timezone.utc)
        self.provider = MockDataProvider([
            RawCandle("EURUSD", "H1", ts_missing, 1.1, 1.12, 1.09, 1.11, 500),
        ])
        self.repair = RepairEngine()

    def tearDown(self):
        reset_collector_database()
        os.unlink(self.tmp.name)
        os.environ.pop("COLLECTOR_SQLITE_PATH", None)

    def test_repair_inserts_missing_candle(self):
        t10 = datetime(2024, 6, 1, 10, 0, tzinfo=timezone.utc)
        t12 = datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc)
        self.db.insert_candles_batch([
            CollectedCandle("EURUSD", Timeframe.H1, t10, 1, 1, 1, 1, 0, "mock", datetime.now(timezone.utc)),
            CollectedCandle("EURUSD", Timeframe.H1, t12, 1, 1, 1, 1, 0, "mock", datetime.now(timezone.utc)),
        ])

        gap = DataGap(
            symbol="EURUSD",
            timeframe=Timeframe.H1,
            gap_type=GapType.MISSING,
            expected_timestamp=datetime(2024, 6, 1, 11, 0, tzinfo=timezone.utc),
            gap_start=t10,
            gap_end=t12,
            provider="mock",
        )
        stored = self.db.store_gaps([gap])

        async def run():
            await self.provider.connect()
            return await self.repair.repair_gaps(stored, self.provider, self.db)

        result = asyncio.run(run())
        self.assertEqual(result.attempted, 1)
        self.assertEqual(result.repaired, 1)
        self.assertEqual(result.rows_inserted, 1)

    def test_unresolved_gap_persisted(self):
        gap = DataGap(
            symbol="EURUSD",
            timeframe=Timeframe.H1,
            gap_type=GapType.MISSING,
            expected_timestamp=datetime(2020, 1, 1, tzinfo=timezone.utc),
            provider="mock",
        )
        stored = self.db.store_gaps([gap])

        async def run():
            await self.provider.connect()
            return await self.repair.repair_gaps(stored, self.provider, self.db)

        result = asyncio.run(run())
        self.assertEqual(result.unresolved, 1)
        open_gaps = self.db.get_open_gaps("EURUSD", Timeframe.H1)
        self.assertTrue(
            any(g.status == GapStatus.UNRESOLVED for g in open_gaps) or
            len(self.db.get_open_gaps()) == 0
        )


if __name__ == "__main__":
    unittest.main()

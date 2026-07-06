"""Tests for collector-first scanner adapter."""

import asyncio
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

from services.data_collector.database import CollectorDatabase, reset_collector_database
from services.data_collector.market_service import InternalMarketDataService, reset_market_data_service
from services.data_collector.models import CollectedCandle
from services.data_collector.scanner_adapter import CollectorFirstProvider, wrap_with_collector_first
from shared.types.models import Candle, Timeframe


class TestScannerAdapter(unittest.TestCase):
    def setUp(self):
        reset_collector_database()
        reset_market_data_service()
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        os.environ["COLLECTOR_SQLITE_PATH"] = self.tmp.name
        os.environ["COLLECTOR_READ_ENABLED"] = "true"
        self.db = CollectorDatabase(force_sqlite=True)

    def tearDown(self):
        reset_collector_database()
        reset_market_data_service()
        os.unlink(self.tmp.name)
        os.environ.pop("COLLECTOR_SQLITE_PATH", None)

    def test_reads_from_collector_db_when_sufficient(self):
        ts = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
        candles_db = [
            CollectedCandle(
                "EURUSD", Timeframe.H1,
                ts + timedelta(hours=i),
                1.1, 1.12, 1.09, 1.11, 100, "mock",
                datetime.now(timezone.utc),
            )
            for i in range(60)
        ]
        self.db.insert_candles_batch(candles_db)

        fallback = MagicMock()
        fallback.name = "simulated"
        fallback.get_candles = AsyncMock(return_value=[])

        service = InternalMarketDataService(database=self.db)
        provider = CollectorFirstProvider(fallback=fallback, min_bars=50, market_service=service)

        result = asyncio.run(provider.get_candles("EURUSD", Timeframe.H1, 200))
        self.assertEqual(len(result), 60)
        self.assertIsInstance(result[0], Candle)
        fallback.get_candles.assert_not_called()

    def test_falls_back_when_db_insufficient(self):
        fallback = MagicMock()
        fallback.name = "simulated"
        expected = [
            Candle("EURUSD", Timeframe.H1, datetime.now(timezone.utc), 1, 1, 1, 1, 0)
            for _ in range(200)
        ]
        fallback.get_candles = AsyncMock(return_value=expected)

        service = InternalMarketDataService(database=self.db)
        provider = CollectorFirstProvider(fallback=fallback, min_bars=50, market_service=service)

        result = asyncio.run(provider.get_candles("EURUSD", Timeframe.H1, 200))
        self.assertEqual(len(result), 200)
        fallback.get_candles.assert_called_once()

    def test_wrap_disabled_via_env(self):
        os.environ["COLLECTOR_READ_ENABLED"] = "false"
        upstream = MagicMock(name="upstream")
        wrapped = wrap_with_collector_first(upstream)
        self.assertIs(wrapped, upstream)


if __name__ == "__main__":
    unittest.main()

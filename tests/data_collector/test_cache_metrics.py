"""Tests for cache fallback and metrics."""

import os
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from services.data_collector.cache import MarketDataCache, reset_market_cache
from services.data_collector.database import CollectorDatabase, reset_collector_database
from services.data_collector.market_service import InternalMarketDataService, reset_market_data_service
from services.data_collector.metrics import CollectorMetrics, reset_collector_metrics
from services.data_collector.models import CollectedCandle
from shared.types.models import Timeframe


class TestCacheAndMetrics(unittest.TestCase):
    def setUp(self):
        reset_collector_database()
        reset_market_cache()
        reset_market_data_service()
        reset_collector_metrics()
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        os.environ["COLLECTOR_SQLITE_PATH"] = self.tmp.name
        self.db = CollectorDatabase(force_sqlite=True)
        ts = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
        self.db.insert_candles_batch([
            CollectedCandle("EURUSD", Timeframe.H1, ts, 1.1, 1.15, 1.05, 1.12, 500, "mock",
                            datetime.now(timezone.utc)),
        ])

    def tearDown(self):
        reset_collector_database()
        reset_market_cache()
        reset_market_data_service()
        reset_collector_metrics()
        os.unlink(self.tmp.name)
        os.environ.pop("COLLECTOR_SQLITE_PATH", None)

    def test_cache_unavailable_falls_back_to_db(self):
        cache = MarketDataCache(redis_url="redis://invalid:9999/0")
        self.assertFalse(cache.available)
        service = InternalMarketDataService(database=self.db, cache=cache)
        candles = service.get_candles("EURUSD", Timeframe.H1)
        self.assertEqual(len(candles), 1)

    def test_metrics_snapshot(self):
        metrics = CollectorMetrics()
        metrics.record_import(duration_ms=100, success=True, rows=50)
        metrics.record_validation_failure(3)
        metrics.record_repair(success=True)
        metrics.record_gaps(2)
        snap = metrics.snapshot()
        self.assertEqual(snap["import_rows_total"], 50)
        self.assertEqual(snap["validation_failures"], 3)
        self.assertIn("repair_success_rate", snap)

    def test_prometheus_export(self):
        metrics = CollectorMetrics()
        metrics.record_import(duration_ms=50, success=True, rows=10)
        output = metrics.export_prometheus()
        self.assertIn("fxnav_import_rows_total 10", output)


if __name__ == "__main__":
    unittest.main()

"""Tests for internal market data API."""

import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from unittest.mock import patch

from services.data_collector.database import CollectorDatabase, reset_collector_database
from services.data_collector.market_service import InternalMarketDataService, reset_market_data_service
from services.data_collector.models import CollectedCandle
from services.data_collector.api import router
from fastapi import FastAPI
from shared.types.models import Timeframe


class TestMarketAPI(unittest.TestCase):
    def setUp(self):
        reset_collector_database()
        reset_market_data_service()
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        os.environ["COLLECTOR_SQLITE_PATH"] = self.tmp.name

        self.db = CollectorDatabase(force_sqlite=True)
        ts = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
        self.db.insert_candles_batch([
            CollectedCandle("EURUSD", Timeframe.H1, ts, 1.1, 1.15, 1.05, 1.12, 500, "mock",
                            datetime.now(timezone.utc)),
        ])

        app = FastAPI()
        app.include_router(router)
        self.service = InternalMarketDataService(database=self.db)
        self.patcher = patch(
            "services.data_collector.api.get_market_data_service",
            return_value=self.service,
        )
        self.patcher.start()
        self.client = TestClient(app)

    def tearDown(self):
        self.patcher.stop()
        reset_collector_database()
        reset_market_data_service()
        os.unlink(self.tmp.name)
        os.environ.pop("COLLECTOR_SQLITE_PATH", None)

    def test_get_candles(self):
        resp = self.client.get("/market/candles", params={"symbol": "EURUSD", "timeframe": "H1"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["candles"][0]["close"], 1.12)

    def test_get_latest(self):
        resp = self.client.get("/market/latest", params={"symbol": "EURUSD", "timeframe": "H1"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["symbol"], "EURUSD")

    def test_get_symbols(self):
        resp = self.client.get("/market/symbols")
        self.assertEqual(resp.status_code, 200)
        self.assertGreater(len(resp.json()["symbols"]), 0)

    def test_get_status(self):
        resp = self.client.get("/market/status")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("candle_count", resp.json())

    def test_get_metrics(self):
        resp = self.client.get("/market/metrics")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("fxnav_import_rows_total", resp.text)


if __name__ == "__main__":
    unittest.main()

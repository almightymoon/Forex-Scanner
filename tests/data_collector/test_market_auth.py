"""Tests for market API authentication."""

import os
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.data_collector.api import router
from services.data_collector.market_service import InternalMarketDataService


class TestMarketAuth(unittest.TestCase):
    def test_blocks_without_key_when_configured(self):
        app = FastAPI()
        app.include_router(router)
        service = InternalMarketDataService.__new__(InternalMarketDataService)

        with patch.dict(os.environ, {"MARKET_API_KEY": "secret-key"}):
            with patch("services.data_collector.api.get_market_data_service", return_value=service):
                with patch.object(service, "get_symbols", return_value=[]):
                    client = TestClient(app)
                    resp = client.get("/market/symbols")
                    self.assertEqual(resp.status_code, 403)

                    resp = client.get("/market/symbols", headers={"X-Market-Api-Key": "secret-key"})
                    self.assertEqual(resp.status_code, 200)

    def test_open_when_key_not_set(self):
        app = FastAPI()
        app.include_router(router)
        service = InternalMarketDataService.__new__(InternalMarketDataService)

        with patch.dict(os.environ, {"MARKET_API_KEY": ""}, clear=False):
            with patch("services.data_collector.api.get_market_data_service", return_value=service):
                with patch.object(service, "get_status", return_value={"healthy": True}):
                    client = TestClient(app)
                    resp = client.get("/market/status")
                    self.assertEqual(resp.status_code, 200)


if __name__ == "__main__":
    unittest.main()

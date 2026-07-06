"""Provider selection, startup validation, and failover tests."""

import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from services.market_data_service.exceptions import MarketDataProviderError, ProviderAuthError
from services.market_data_service.factory import (
    _ordered_provider_keys,
    create_provider,
    validate_startup,
)
from services.market_data_service.provider_chain import ProviderChain
from shared.config.market import is_simulated_mode, reload_market_config
from shared.types.models import Timeframe


class TestStartupValidation(unittest.TestCase):
    def tearDown(self):
        reload_market_config()

    @patch.dict(os.environ, {"ENABLE_SIMULATED_DATA": "false", "TWELVE_DATA_API_KEY": "", "POLYGON_API_KEY": ""}, clear=False)
    def test_startup_fails_without_providers(self):
        reload_market_config()
        with self.assertRaises(ProviderAuthError):
            validate_startup()

    @patch.dict(os.environ, {"ENABLE_SIMULATED_DATA": "true"}, clear=False)
    def test_startup_allows_simulated_without_keys(self):
        reload_market_config()
        validate_startup()

    @patch.dict(os.environ, {"ENABLE_SIMULATED_DATA": "false", "TWELVE_DATA_API_KEY": "key"}, clear=False)
    def test_startup_passes_with_twelve_data_key(self):
        reload_market_config()
        validate_startup()


class TestProviderOrdering(unittest.TestCase):
    def tearDown(self):
        reload_market_config()

    @patch.dict(
        os.environ,
        {
            "ENABLE_SIMULATED_DATA": "false",
            "TWELVE_DATA_API_KEY": "td",
            "POLYGON_API_KEY": "",
        },
        clear=False,
    )
    def test_twelve_data_only_when_polygon_not_configured(self):
        reload_market_config()
        keys = _ordered_provider_keys()
        self.assertEqual(keys, ["twelvedata"])

    @patch.dict(
        os.environ,
        {
            "ENABLE_SIMULATED_DATA": "false",
            "TWELVE_DATA_API_KEY": "td",
            "POLYGON_API_KEY": "pg",
        },
        clear=False,
    )
    def test_both_providers_when_fallback_enabled(self):
        with patch("shared.config.market._load_yaml") as mock_yaml:
            mock_yaml.return_value = {
                "market_data": {
                    "default_provider": "twelvedata",
                    "providers": ["twelvedata", "polygon"],
                    "fallback_enabled": True,
                }
            }
            reload_market_config()
            keys = _ordered_provider_keys()
            self.assertEqual(keys, ["twelvedata", "polygon"])

    @patch.dict(
        os.environ,
        {"ENABLE_SIMULATED_DATA": "false", "TWELVE_DATA_API_KEY": "", "POLYGON_API_KEY": "pg"},
        clear=False,
    )
    def test_polygon_primary_when_twelve_data_missing(self):
        reload_market_config()
        keys = _ordered_provider_keys()
        self.assertEqual(keys, ["polygon"])


class TestSimulatedMode(unittest.TestCase):
    def tearDown(self):
        reload_market_config()

    @patch.dict(os.environ, {"ENABLE_SIMULATED_DATA": "false", "ENVIRONMENT": "development"}, clear=False)
    def test_simulated_not_inferred_from_environment(self):
        reload_market_config()
        self.assertFalse(is_simulated_mode())

    @patch.dict(os.environ, {"ENABLE_SIMULATED_DATA": "true"}, clear=False)
    def test_simulated_only_when_explicit(self):
        reload_market_config()
        self.assertTrue(is_simulated_mode())
        provider = create_provider()
        self.assertEqual(provider.name, "simulated")


class TestProviderFailover(unittest.IsolatedAsyncioTestCase):
    async def test_polygon_used_when_twelve_data_fails(self):
        twelve = MagicMock()
        twelve.name = "twelvedata"
        twelve.get_candles = AsyncMock(
            side_effect=MarketDataProviderError("twelvedata", "rate limited")
        )

        polygon = MagicMock()
        polygon.name = "polygon"
        polygon.get_candles = AsyncMock(return_value=[])

        chain = ProviderChain([twelve, polygon], allow_fallback=True)
        await chain.get_candles("EURUSD", Timeframe.H1, 10)

        self.assertEqual(chain.active_provider, "polygon")
        polygon.get_candles.assert_awaited_once()

    async def test_no_failover_when_disabled(self):
        twelve = MagicMock()
        twelve.name = "twelvedata"
        twelve.get_candles = AsyncMock(
            side_effect=MarketDataProviderError("twelvedata", "unavailable")
        )

        polygon = MagicMock()
        polygon.name = "polygon"
        polygon.get_candles = AsyncMock(return_value=[])

        chain = ProviderChain([twelve, polygon], allow_fallback=False)
        with self.assertRaises(MarketDataProviderError):
            await chain.get_candles("EURUSD", Timeframe.H1, 10)

        polygon.get_candles.assert_not_called()


if __name__ == "__main__":
    unittest.main()

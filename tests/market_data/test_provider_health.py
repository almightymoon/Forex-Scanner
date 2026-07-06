"""Market data provider health and factory tests."""

import os
import unittest
from unittest.mock import patch

from services.market_data_service.exceptions import ProviderAuthError, ProviderStatus
from services.market_data_service.factory import _validate_provider_key, validate_startup
from services.market_data_service.provider_health import ProviderHealthTracker
from shared.config.market import is_simulated_mode, reload_market_config


class TestProviderHealth(unittest.TestCase):
    def test_record_success_and_failure(self):
        ProviderHealthTracker.record_success("test_provider", 120.5)
        snap = ProviderHealthTracker.snapshot("test_provider")
        self.assertEqual(snap["provider_status"], ProviderStatus.HEALTHY.value)
        self.assertIsNotNone(snap["last_success"])

        ProviderHealthTracker.record_failure(
            "test_provider",
            ProviderStatus.RATE_LIMITED,
            "429 Too Many Requests",
            200.0,
        )
        snap = ProviderHealthTracker.snapshot("test_provider")
        self.assertEqual(snap["provider_status"], ProviderStatus.RATE_LIMITED.value)
        self.assertEqual(snap["last_error"], "429 Too Many Requests")


class TestFactorySelection(unittest.TestCase):
    def tearDown(self):
        reload_market_config()

    def test_simulated_only_when_explicit(self):
        if os.getenv("ENABLE_SIMULATED_DATA") == "true":
            self.assertTrue(is_simulated_mode())
        else:
            self.assertFalse(is_simulated_mode())

    def test_missing_api_key_validation(self):
        if not os.getenv("TWELVE_DATA_API_KEY"):
            with self.assertRaises(ProviderAuthError):
                _validate_provider_key("twelvedata")

    @patch.dict(os.environ, {"ENABLE_SIMULATED_DATA": "false", "TWELVE_DATA_API_KEY": "", "POLYGON_API_KEY": ""}, clear=False)
    def test_validate_startup_requires_keys(self):
        reload_market_config()
        with self.assertRaises(ProviderAuthError):
            validate_startup()


if __name__ == "__main__":
    unittest.main()

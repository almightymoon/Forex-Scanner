"""Market data provider health and factory tests."""

import os
import unittest

from services.market_data_service.exceptions import ProviderAuthError, ProviderStatus
from services.market_data_service.provider_health import ProviderHealthTracker
from shared.config.market import get_market_config, is_simulated_mode


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
    def test_simulated_mode_flag(self):
        if os.getenv("ENVIRONMENT") == "development" or os.getenv("ENABLE_SIMULATED_DATA") == "true":
            self.assertTrue(is_simulated_mode())

    def test_missing_api_key_validation(self):
        from services.market_data_service.factory import _validate_provider_key
        if not os.getenv("TWELVE_DATA_API_KEY"):
            with self.assertRaises(ProviderAuthError):
                _validate_provider_key("twelvedata")


if __name__ == "__main__":
    unittest.main()

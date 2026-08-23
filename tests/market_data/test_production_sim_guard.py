"""Production must never run with simulated market data."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from shared.config.market import (
    SimulatedDataForbiddenError,
    assert_simulated_data_allowed,
    reload_market_config,
)
from services.market_data_service.factory import validate_startup


class TestProductionSimGuard(unittest.TestCase):
    def tearDown(self):
        reload_market_config()

    @patch.dict(
        os.environ,
        {
            "ENVIRONMENT": "production",
            "ENABLE_SIMULATED_DATA": "true",
            "TWELVE_DATA_API_KEY": "",
            "POLYGON_API_KEY": "",
        },
        clear=False,
    )
    def test_assert_blocks_production_sim(self):
        reload_market_config()
        with self.assertRaises(SimulatedDataForbiddenError):
            assert_simulated_data_allowed()

    @patch.dict(
        os.environ,
        {
            "ENVIRONMENT": "production",
            "ENABLE_SIMULATED_DATA": "true",
        },
        clear=False,
    )
    def test_startup_blocks_production_sim(self):
        reload_market_config()
        with self.assertRaises(SimulatedDataForbiddenError):
            validate_startup()

    @patch.dict(
        os.environ,
        {
            "ENVIRONMENT": "development",
            "ENABLE_SIMULATED_DATA": "true",
        },
        clear=False,
    )
    def test_dev_allows_sim(self):
        reload_market_config()
        assert_simulated_data_allowed()
        validate_startup()

    @patch.dict(
        os.environ,
        {
            "ENVIRONMENT": "production",
            "ENABLE_SIMULATED_DATA": "false",
            "TWELVE_DATA_API_KEY": "k",
        },
        clear=False,
    )
    def test_production_real_provider_ok(self):
        reload_market_config()
        assert_simulated_data_allowed()
        validate_startup()


if __name__ == "__main__":
    unittest.main()

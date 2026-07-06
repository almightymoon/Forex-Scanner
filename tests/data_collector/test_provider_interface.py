"""Unit tests for provider interface compliance."""

import inspect
import unittest
from abc import ABC

from services.data_collector.providers.base_provider import BaseDataProvider
from services.data_collector.providers.dukascopy import DukascopyDataProvider
from services.data_collector.providers.mt5 import MT5DataProvider
from tests.data_collector.mock_provider import MockDataProvider


REQUIRED_METHODS = ("connect", "download_history", "stream_live", "health", "disconnect")


class TestProviderInterface(unittest.TestCase):
    def test_base_is_abstract(self):
        self.assertTrue(issubclass(BaseDataProvider, ABC))
        with self.assertRaises(TypeError):
            BaseDataProvider()  # type: ignore

    def _assert_provider_compliance(self, cls: type[BaseDataProvider]) -> None:
        for method in REQUIRED_METHODS:
            self.assertTrue(hasattr(cls, method), f"{cls.__name__} missing {method}")
            fn = getattr(cls, method)
            self.assertTrue(callable(fn))

        provider = cls()
        self.assertIsInstance(provider.name, str)
        self.assertTrue(len(provider.name) > 0)

    def test_mt5_implements_interface(self):
        self._assert_provider_compliance(MT5DataProvider)

    def test_dukascopy_implements_interface(self):
        self._assert_provider_compliance(DukascopyDataProvider)

    def test_mock_implements_interface(self):
        self._assert_provider_compliance(MockDataProvider)

    def test_download_history_signature(self):
        sig = inspect.signature(BaseDataProvider.download_history)
        params = list(sig.parameters.keys())
        self.assertIn("symbol", params)
        self.assertIn("timeframe", params)
        self.assertIn("start", params)
        self.assertIn("end", params)


if __name__ == "__main__":
    unittest.main()

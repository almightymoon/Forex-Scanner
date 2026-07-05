"""HTTP client error classification tests."""

import unittest
from unittest.mock import MagicMock, patch

from services.market_data_service.exceptions import ProviderAuthError, ProviderRateLimitError
from services.market_data_service.http_client import http_get_json


class TestHttpClient(unittest.TestCase):
    @patch("services.market_data_service.http_client.urllib.request.urlopen")
    def test_rate_limit_raises(self, mock_urlopen):
        import urllib.error
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="http://test", code=429, msg="Too Many Requests", hdrs={}, fp=MagicMock(read=lambda: b'{"error":"rate limit"}')
        )
        with self.assertRaises(ProviderRateLimitError):
            http_get_json("http://test", "twelvedata", symbol="EURUSD", timeframe="H1")

    @patch("services.market_data_service.http_client.urllib.request.urlopen")
    def test_invalid_api_key_raises(self, mock_urlopen):
        import urllib.error
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="http://test", code=401, msg="Unauthorized", hdrs={}, fp=MagicMock(read=lambda: b'{"error":"invalid api key"}')
        )
        with self.assertRaises(ProviderAuthError):
            http_get_json("http://test", "twelvedata", symbol="EURUSD", timeframe="H1")


if __name__ == "__main__":
    unittest.main()

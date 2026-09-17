"""Collector-first adapter health should follow the upstream OHLC provider."""

from shared.types.models import Timeframe
from services.data_collector.scanner_adapter import CollectorFirstProvider
from services.market_data_service.provider import MarketDataProvider


class _FakeUpstream(MarketDataProvider):
    name = "twelvedata"

    async def get_candles(self, symbol, timeframe, count=200):
        return []

    def health_snapshot(self):
        return {
            "provider_name": self.name,
            "provider_status": "healthy",
            "latency_ms": 12.0,
        }

    def monitored_health(self):
        return {self.name: {"configured": True, "status": "healthy", "latency_ms": 12.0}}


def test_collector_health_follows_fallback():
    adapter = CollectorFirstProvider(fallback=_FakeUpstream())
    snap = adapter.health_snapshot()
    assert snap["provider_status"] == "healthy"
    assert snap["fallback_provider"] == "twelvedata"
    assert snap["collector_cache"] == "optional"
    assert adapter.underlying_provider == "twelvedata"
    assert adapter.monitored_health()["twelvedata"]["status"] == "healthy"

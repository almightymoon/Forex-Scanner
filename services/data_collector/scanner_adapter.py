"""Scanner adapter — read validated candles from collector DB, fallback to external providers."""

import logging
import os
from datetime import datetime

from services.data_collector.market_service import get_market_data_service
from services.market_data_service.provider import MarketDataProvider
from shared.types.models import Candle, Timeframe

logger = logging.getLogger("fxnav.collector_adapter")

MIN_BARS_DEFAULT = 50


def collector_read_enabled() -> bool:
    return os.getenv("COLLECTOR_READ_ENABLED", "true").lower() == "true"


class CollectorFirstProvider(MarketDataProvider):
    """
    Primary read path for the scanner.

    Reads from the collector database (validated, normalized candles).
    Falls back to the configured external provider when the DB has insufficient data.
    """

    name = "collector_db"

    def __init__(
        self,
        fallback: MarketDataProvider,
        min_bars: int = MIN_BARS_DEFAULT,
        market_service=None,
    ):
        self.fallback = fallback
        self.min_bars = min_bars
        self._service = market_service

    async def get_candles(
        self, symbol: str, timeframe: Timeframe, count: int = 200
    ) -> list[Candle]:
        service = self._service or get_market_data_service()
        rows = service.get_candles(symbol.upper(), timeframe, limit=count)
        if len(rows) >= min(self.min_bars, count):
            logger.debug(
                "collector DB hit: %s %s (%d bars)",
                symbol, timeframe.value, len(rows),
            )
            return [self._to_candle(r) for r in rows]

        logger.info(
            "collector DB has %d/%d bars for %s %s — falling back to %s",
            len(rows), count, symbol, timeframe.value, self.fallback.name,
        )
        return await self.fallback.get_candles(symbol, timeframe, count)

    async def get_live_prices(self) -> dict[str, float]:
        if hasattr(self.fallback, "get_live_prices"):
            return await self.fallback.get_live_prices()
        return {}

    async def stream_ticks(self, symbols: list[str]):
        if hasattr(self.fallback, "stream_ticks"):
            async for tick in self.fallback.stream_ticks(symbols):
                yield tick
        return

    def health_snapshot(self) -> dict:
        """Collector is a cache layer — report fallback provider health as primary signal."""
        fb = {}
        if hasattr(self.fallback, "health_snapshot"):
            fb = self.fallback.health_snapshot() or {}
        elif hasattr(self.fallback, "provider") and hasattr(self.fallback.provider, "health_snapshot"):
            fb = self.fallback.provider.health_snapshot() or {}

        status = fb.get("provider_status", "unknown")
        fallback_name = (
            getattr(self.fallback, "underlying_provider", None)
            or getattr(self.fallback, "name", "unknown")
        )
        # Empty collector DB is normal when COLLECTOR_DAEMON is off — not an outage.
        return {
            "provider_name": self.name,
            "provider_status": status if status not in (None, "") else "healthy",
            "latency_ms": fb.get("latency_ms"),
            "last_success": fb.get("last_success"),
            "last_failure": fb.get("last_failure"),
            "last_error": fb.get("last_error"),
            "fallback_used": True,
            "fallback_provider": str(fallback_name).replace("service:", ""),
            "collector_cache": "optional",
        }

    def monitored_providers_health(self) -> dict:
        if hasattr(self.fallback, "monitored_providers_health"):
            return self.fallback.monitored_providers_health()
        if hasattr(self.fallback, "monitored_health"):
            return self.fallback.monitored_health()
        return {}

    # Alias used by MarketDataService
    def monitored_health(self) -> dict:
        return self.monitored_providers_health()

    def is_simulated(self) -> bool:
        if hasattr(self.fallback, "is_simulated"):
            return bool(self.fallback.is_simulated())
        return False

    @property
    def underlying_provider(self) -> str:
        name = getattr(self.fallback, "underlying_provider", None) or getattr(
            self.fallback, "name", "unknown"
        )
        return str(name).replace("service:", "")

    @staticmethod
    def _to_candle(row: dict) -> Candle:
        ts = row["timestamp"]
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return Candle(
            symbol=row["symbol"],
            timeframe=Timeframe(row["timeframe"]),
            timestamp=ts,
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=int(row.get("volume", 0)),
        )


def wrap_with_collector_first(provider: MarketDataProvider) -> MarketDataProvider:
    """Wrap an upstream provider with collector-first reads when enabled."""
    if not collector_read_enabled():
        return provider
    return CollectorFirstProvider(fallback=provider)

"""Composed market data service — cache, validation, storage, health passthrough."""

import logging
import time
from datetime import datetime
from typing import AsyncGenerator, Optional

from shared.config.market import is_simulated_mode
from shared.types.models import Candle, Tick, Timeframe

from .cache import MarketDataCache
from .exceptions import MarketDataProviderError
from .provider import MarketDataProvider
from .provider_health import ProviderHealthTracker
from .storage import CandleStorage
from .validator import DataValidator

logger = logging.getLogger("fxnav.market_data")


class MarketDataService(MarketDataProvider):
    """Production facade used by the scanner."""

    name = "service"

    def __init__(
        self,
        provider: MarketDataProvider,
        cache: Optional[MarketDataCache] = None,
        storage: Optional[CandleStorage] = None,
        validator: Optional[DataValidator] = None,
    ):
        self.provider = provider
        self.cache = cache or MarketDataCache()
        self.storage = storage or CandleStorage()
        self.validator = validator or DataValidator()
        self.name = f"service:{provider.name}"

    @property
    def underlying_provider(self) -> str:
        return self.provider.name

    def health_snapshot(self) -> dict:
        return ProviderHealthTracker.snapshot(self.provider.name)

    def is_simulated(self) -> bool:
        return is_simulated_mode() or self.provider.name == "simulated"

    async def get_candles(
        self, symbol: str, timeframe: Timeframe, count: int = 200
    ) -> list[Candle]:
        cache_key = f"candles:{symbol}:{timeframe.value}:{count}"
        cached = self.cache.get(cache_key)
        if cached:
            return cached

        start = time.perf_counter()
        try:
            candles = await self.provider.get_candles(symbol, timeframe, count)
        except MarketDataProviderError:
            raise
        except Exception as exc:
            logger.exception(
                "MarketDataService candle fetch failed | provider=%s symbol=%s timeframe=%s",
                self.provider.name,
                symbol,
                timeframe.value,
            )
            raise MarketDataProviderError(
                self.provider.name,
                str(exc),
                symbol=symbol,
                timeframe=timeframe.value,
            ) from exc

        latency_ms = (time.perf_counter() - start) * 1000
        logger.debug(
            "Candles fetched | provider=%s symbol=%s count=%d latency_ms=%.1f",
            self.provider.name,
            symbol,
            len(candles),
            latency_ms,
        )

        candles = self.validator.validate_candles(candles)
        if candles:
            self.storage.save(symbol, timeframe, candles)
            self.cache.set(cache_key, candles)
        return candles

    async def get_historical_candles(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> list[Candle]:
        cache_key = f"hist:{symbol}:{timeframe.value}:{start.isoformat()}:{end.isoformat()}"
        cached = self.cache.get(cache_key)
        if cached:
            return cached

        if hasattr(self.provider, "get_historical_candles"):
            candles = await self.provider.get_historical_candles(symbol, timeframe, start, end)
        else:
            candles = await self.get_candles(symbol, timeframe, 500)
            candles = [c for c in candles if start <= c.timestamp <= end]

        candles = self.validator.validate_candles(candles)
        if candles:
            self.cache.set(cache_key, candles)
        return candles

    async def stream_ticks(self, symbols: list[str]) -> AsyncGenerator[Tick, None]:
        async for tick in self.provider.stream_ticks(symbols):
            if self.validator.validate_tick(tick):
                yield tick

    async def get_live_prices(self) -> dict[str, float]:
        cache_key = "live_prices"
        cached = self.cache.get(cache_key)
        if cached:
            return cached

        if hasattr(self.provider, "get_live_prices"):
            prices = await self.provider.get_live_prices()
            self.cache.set(cache_key, prices)
            return prices
        return {}

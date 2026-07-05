"""Composed market data service — cache, validation, storage on top of any provider."""

from datetime import datetime
from typing import AsyncGenerator, Optional

from shared.types.models import Candle, Tick, Timeframe

from .cache import MarketDataCache
from .provider import MarketDataProvider
from .storage import CandleStorage
from .validator import DataValidator


class MarketDataService(MarketDataProvider):
    """
    Production facade used by the scanner.
    Wraps a swappable provider with caching, validation, and storage.
    """

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

    async def get_candles(
        self, symbol: str, timeframe: Timeframe, count: int = 200
    ) -> list[Candle]:
        cache_key = f"candles:{symbol}:{timeframe.value}:{count}"
        cached = self.cache.get(cache_key)
        if cached:
            return cached

        candles = await self.provider.get_candles(symbol, timeframe, count)
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

"""Explicit provider failover — Twelve Data → Polygon, never silent."""

import logging
import os
from collections.abc import Awaitable, Callable
from typing import TypeVar

from .exceptions import MarketDataProviderError, ProviderStatus
from .provider import MarketDataProvider
from .provider_health import ProviderHealthTracker

logger = logging.getLogger("fxnav.market_data")

T = TypeVar("T")

MONITORED_PROVIDERS = ("twelvedata", "polygon")


class ProviderChain(MarketDataProvider):
    """Try providers in priority order; log every failover explicitly."""

    def __init__(self, providers: list[MarketDataProvider], allow_fallback: bool):
        if not providers:
            raise MarketDataProviderError(
                "market_data",
                "No market data providers available — configure API keys or enable simulation",
            )
        self.providers = providers
        self.allow_fallback = allow_fallback
        self._active = providers[0]
        self.name = self._active.name

    @property
    def active_provider(self) -> str:
        return self._active.name

    def health_snapshot(self) -> dict:
        return ProviderHealthTracker.snapshot(self._active.name)

    def monitored_health(self) -> dict[str, dict]:
        """Health for Twelve Data and Polygon only."""
        result: dict[str, dict] = {}
        for key in MONITORED_PROVIDERS:
            snap = ProviderHealthTracker.snapshot(key)
            configured = (
                bool(os.getenv("TWELVE_DATA_API_KEY", ""))
                if key == "twelvedata"
                else bool(os.getenv("POLYGON_API_KEY", ""))
            )
            status = snap.get("provider_status", "unknown")
            if not configured:
                status = "not_configured"
            result[key] = {
                "configured": configured,
                "status": status,
                "latency_ms": snap.get("latency_ms"),
            }
        return result

    async def get_candles(self, symbol, timeframe, count: int = 200):
        async def _fetch(provider: MarketDataProvider):
            return await provider.get_candles(symbol, timeframe, count)

        return await self._with_failover(
            _fetch,
            operation="get_candles",
            symbol=symbol,
            timeframe=timeframe.value,
        )

    async def get_historical_candles(self, symbol, timeframe, start, end):
        async def _fetch(provider: MarketDataProvider):
            if hasattr(provider, "get_historical_candles"):
                return await provider.get_historical_candles(symbol, timeframe, start, end)
            return await provider.get_candles(symbol, timeframe, 500)

        return await self._with_failover(
            _fetch,
            operation="get_historical_candles",
            symbol=symbol,
            timeframe=timeframe.value,
        )

    async def get_live_prices(self) -> dict[str, float]:
        async def _fetch(provider: MarketDataProvider):
            return await provider.get_live_prices()

        return await self._with_failover(
            _fetch,
            operation="get_live_prices",
        )

    def _eligible_providers(self) -> list[MarketDataProvider]:
        """Skip rate-limited primaries so Polygon is used immediately after a 429."""
        if not self.allow_fallback or len(self.providers) == 1:
            return self.providers

        eligible: list[MarketDataProvider] = []
        for provider in self.providers:
            snap = ProviderHealthTracker.snapshot(provider.name)
            status = snap.get("provider_status")
            if status in (ProviderStatus.RATE_LIMITED.value, ProviderStatus.AUTHENTICATION_FAILED.value):
                logger.info("Skipping unhealthy provider %s (status=%s)", provider.name, status)
                continue
            eligible.append(provider)
        return eligible or self.providers

    async def _with_failover(
        self,
        fn: Callable[[MarketDataProvider], Awaitable[T]],
        operation: str,
        symbol: str | None = None,
        timeframe: str | None = None,
    ) -> T:
        last_error: MarketDataProviderError | None = None
        providers = self._eligible_providers()

        for idx, provider in enumerate(providers):
            if idx > 0:
                if not self.allow_fallback:
                    break
                logger.warning(
                    "Market data failover | operation=%s from=%s to=%s reason=%s",
                    operation,
                    providers[idx - 1].name,
                    provider.name,
                    last_error,
                )

            try:
                result = await fn(provider)
                self._active = provider
                if idx > 0:
                    logger.info(
                        "Market data recovered via failover | provider=%s operation=%s",
                        provider.name,
                        operation,
                    )
                return result
            except MarketDataProviderError as exc:
                last_error = exc
                continue

        if last_error:
            raise last_error

        detail = f"{operation} failed"
        if symbol:
            detail += f" for {symbol}"
        raise MarketDataProviderError(
            "market_data",
            detail,
            symbol=symbol,
            timeframe=timeframe,
        )

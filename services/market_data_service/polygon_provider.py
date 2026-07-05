"""Polygon.io provider stub — swap in when POLYGON_API_KEY is set."""

import json
import urllib.request
from datetime import datetime, timezone
from typing import AsyncGenerator

from shared.configs.settings import get_settings
from shared.types.models import Candle, Tick, Timeframe

from .frankfurter_provider import FrankfurterProvider
from .provider import MarketDataProvider

settings = get_settings()


class PolygonProvider(MarketDataProvider):
    name = "polygon"

    def __init__(self):
        self._api_key = settings.POLYGON_API_KEY
        self._fallback = FrankfurterProvider()

    async def get_candles(
        self, symbol: str, timeframe: Timeframe, count: int = 200
    ) -> list[Candle]:
        if not self._api_key:
            return await self._fallback.get_candles(symbol, timeframe, count)

        try:
            candles = await self._fetch_aggregates(symbol, timeframe, count)
            if candles:
                return candles
        except Exception:
            pass

        return await self._fallback.get_candles(symbol, timeframe, count)

    async def get_live_prices(self) -> dict[str, float]:
        return await self._fallback.get_live_prices()

    async def stream_ticks(self, symbols: list[str]) -> AsyncGenerator[Tick, None]:
        async for tick in self._fallback.stream_ticks(symbols):
            yield tick

    async def _fetch_aggregates(
        self, symbol: str, timeframe: Timeframe, count: int
    ) -> list[Candle]:
        ticker = f"C:{symbol}"
        multiplier, span = _polygon_tf(timeframe)
        url = (
            f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/"
            f"{multiplier}/{span}/2024-01-01/2025-12-31"
            f"?adjusted=true&sort=asc&limit={min(count, 500)}&apiKey={self._api_key}"
        )
        import asyncio
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(None, _http_get, url)

        results = data.get("results", [])
        candles: list[Candle] = []
        for bar in results:
            ts = datetime.fromtimestamp(bar["t"] / 1000, tz=timezone.utc)
            candles.append(
                Candle(
                    symbol=symbol,
                    timeframe=timeframe,
                    timestamp=ts,
                    open=bar["o"],
                    high=bar["h"],
                    low=bar["l"],
                    close=bar["c"],
                    volume=int(bar.get("v", 0)),
                )
            )
        return candles


def _polygon_tf(timeframe: Timeframe) -> tuple[int, str]:
    mapping = {
        Timeframe.M1: (1, "minute"),
        Timeframe.M5: (5, "minute"),
        Timeframe.M15: (15, "minute"),
        Timeframe.H1: (1, "hour"),
        Timeframe.H4: (4, "hour"),
        Timeframe.D1: (1, "day"),
    }
    return mapping.get(timeframe, (1, "hour"))


def _http_get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "FXNavigators/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())

"""Polygon.io provider — real aggregate OHLCV."""

import asyncio
from datetime import datetime, timedelta, timezone

from shared.configs.settings import get_settings
from shared.types.models import Candle, Timeframe

from .exceptions import MarketDataProviderError, ProviderAuthError
from .http_client import http_get_json
from .provider import MarketDataProvider

settings = get_settings()


class PolygonProvider(MarketDataProvider):
    name = "polygon"

    def __init__(self):
        self._api_key = settings.POLYGON_API_KEY
        if not self._api_key:
            raise ProviderAuthError("polygon", "POLYGON_API_KEY is not configured")

    async def get_candles(
        self, symbol: str, timeframe: Timeframe, count: int = 200
    ) -> list[Candle]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._fetch_aggregates_sync, symbol, timeframe, count)

    async def get_live_prices(self) -> dict[str, float]:
        from .frankfurter_provider import FrankfurterProvider
        return await FrankfurterProvider().get_live_prices()

    def _fetch_aggregates_sync(
        self, symbol: str, timeframe: Timeframe, count: int
    ) -> list[Candle]:
        ticker = f"C:{symbol}"
        multiplier, span = _polygon_tf(timeframe)
        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=365)
        url = (
            f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/"
            f"{multiplier}/{span}/{start}/{end}"
            f"?adjusted=true&sort=asc&limit={min(count, 500)}&apiKey={self._api_key}"
        )
        data = http_get_json(url, self.name, symbol=symbol, timeframe=timeframe.value)
        results = data.get("results", [])
        if not results:
            raise MarketDataProviderError(
                self.name,
                "Empty candle response from Polygon",
                symbol=symbol,
                timeframe=timeframe.value,
            )

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

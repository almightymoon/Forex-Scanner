"""Twelve Data API provider — real intraday OHLCV only."""

import asyncio
from datetime import datetime, timezone

from shared.configs.settings import get_settings
from shared.types.models import Candle, Timeframe

from .exceptions import MarketDataProviderError, ProviderAuthError
from .http_client import http_get_json
from .provider import MarketDataProvider

settings = get_settings()

TF_MAP = {
    Timeframe.M1: "1min",
    Timeframe.M5: "5min",
    Timeframe.M15: "15min",
    Timeframe.M30: "30min",
    Timeframe.H1: "1h",
    Timeframe.H4: "4h",
    Timeframe.D1: "1day",
}


def _format_symbol(symbol: str) -> str:
    if len(symbol) == 6:
        return f"{symbol[:3]}/{symbol[3:]}"
    if symbol == "XAUUSD":
        return "XAU/USD"
    if symbol == "XAGUSD":
        return "XAG/USD"
    return symbol


class TwelveDataProvider(MarketDataProvider):
    name = "twelvedata"
    BASE_URL = "https://api.twelvedata.com/time_series"

    def __init__(self):
        self._api_key = settings.TWELVE_DATA_API_KEY
        if not self._api_key:
            raise ProviderAuthError("twelvedata", "TWELVE_DATA_API_KEY is not configured")

    async def get_candles(
        self, symbol: str, timeframe: Timeframe, count: int = 200
    ) -> list[Candle]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._fetch_candles_sync, symbol, timeframe, count)

    async def get_live_prices(self) -> dict[str, float]:
        from .frankfurter_provider import FrankfurterProvider
        return await FrankfurterProvider().get_live_prices()

    def _fetch_candles_sync(
        self, symbol: str, timeframe: Timeframe, count: int
    ) -> list[Candle]:
        interval = TF_MAP.get(timeframe, "1h")
        formatted = _format_symbol(symbol)
        url = (
            f"{self.BASE_URL}?symbol={formatted}&interval={interval}"
            f"&outputsize={min(count, 500)}&apikey={self._api_key}"
        )
        data = http_get_json(url, self.name, symbol=symbol, timeframe=timeframe.value)

        if data.get("status") == "error":
            raise MarketDataProviderError(
                self.name,
                data.get("message", "Twelve Data error"),
                symbol=symbol,
                timeframe=timeframe.value,
            )

        values = data.get("values", [])
        if not values:
            raise MarketDataProviderError(
                self.name,
                "Empty candle response from Twelve Data",
                symbol=symbol,
                timeframe=timeframe.value,
            )

        candles: list[Candle] = []
        for v in reversed(values):
            candles.append(
                Candle(
                    symbol=symbol,
                    timeframe=timeframe,
                    timestamp=datetime.fromisoformat(v["datetime"]).replace(tzinfo=timezone.utc),
                    open=float(v["open"]),
                    high=float(v["high"]),
                    low=float(v["low"]),
                    close=float(v["close"]),
                    volume=int(float(v.get("volume", 0))),
                )
            )
        return candles

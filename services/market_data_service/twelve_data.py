"""Twelve Data API provider for real intraday candles."""

import json
import urllib.request
from datetime import datetime, timezone

from shared.configs.settings import get_settings
from shared.types.models import Candle, Timeframe

from .live import LiveMarketData

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


class TwelveDataProvider(LiveMarketData):
    """Fetches real OHLCV candles from Twelve Data API."""

    BASE_URL = "https://api.twelvedata.com/time_series"

    def __init__(self):
        super().__init__()
        self._api_key = settings.TWELVE_DATA_API_KEY
        self._fallback = LiveMarketData()

    async def get_candles(
        self, symbol: str, timeframe: Timeframe, count: int = 200
    ) -> list[Candle]:
        if not self._api_key:
            return await self._fallback.get_candles(symbol, timeframe, count)

        cache_key = f"td_{symbol}_{timeframe.value}"
        try:
            candles = await self._fetch_candles(symbol, timeframe, count)
            if candles:
                self._candle_cache[cache_key] = candles
                return candles
        except Exception:
            pass

        return await self._fallback.get_candles(symbol, timeframe, count)

    async def _fetch_candles(
        self, symbol: str, timeframe: Timeframe, count: int
    ) -> list[Candle]:
        import asyncio

        interval = TF_MAP.get(timeframe, "1h")
        formatted = _format_symbol(symbol)
        url = (
            f"{self.BASE_URL}?symbol={formatted}&interval={interval}"
            f"&outputsize={min(count, 500)}&apikey={self._api_key}"
        )
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(None, self._http_get, url)

        if data.get("status") == "error":
            raise ValueError(data.get("message", "Twelve Data error"))

        values = data.get("values", [])
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

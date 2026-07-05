"""OANDA v20 REST provider — real historical OHLC candles."""

import asyncio
from datetime import datetime, timezone

from shared.configs.settings import get_settings
from shared.types.models import Candle, Timeframe

from .exceptions import MarketDataProviderError, ProviderAuthError
from .http_client import http_get_json
from .provider import MarketDataProvider

settings = get_settings()

GRANULARITY = {
    Timeframe.M1: "M1",
    Timeframe.M5: "M5",
    Timeframe.M15: "M15",
    Timeframe.M30: "M30",
    Timeframe.H1: "H1",
    Timeframe.H4: "H4",
    Timeframe.D1: "D",
}


def _oanda_instrument(symbol: str) -> str:
    if len(symbol) == 6:
        return f"{symbol[:3]}_{symbol[3:]}"
    if symbol == "XAUUSD":
        return "XAU_USD"
    if symbol == "XAGUSD":
        return "XAG_USD"
    return symbol


class OandaProvider(MarketDataProvider):
    name = "oanda"
    BASE_URL = "https://api-fxpractice.oanda.com/v3"

    def __init__(self):
        self._api_key = settings.OANDA_API_KEY
        self._account_id = settings.OANDA_ACCOUNT_ID
        if not self._api_key or not self._account_id:
            raise ProviderAuthError("oanda", "OANDA_API_KEY and OANDA_ACCOUNT_ID are required")

    async def get_candles(
        self, symbol: str, timeframe: Timeframe, count: int = 200
    ) -> list[Candle]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._fetch_candles_sync, symbol, timeframe, count)

    async def get_live_prices(self) -> dict[str, float]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._fetch_prices_sync)

    def _fetch_candles_sync(
        self, symbol: str, timeframe: Timeframe, count: int
    ) -> list[Candle]:
        instrument = _oanda_instrument(symbol)
        granularity = GRANULARITY.get(timeframe, "H1")
        url = (
            f"{self.BASE_URL}/instruments/{instrument}/candles"
            f"?count={min(count, 500)}&granularity={granularity}&price=M"
        )
        headers = {"Authorization": f"Bearer {self._api_key}"}
        data = http_get_json(url, self.name, symbol=symbol, timeframe=timeframe.value, headers=headers)
        candles_raw = data.get("candles", [])
        if not candles_raw:
            raise MarketDataProviderError(
                self.name,
                "Empty candle response from OANDA",
                symbol=symbol,
                timeframe=timeframe.value,
            )

        candles: list[Candle] = []
        for c in candles_raw:
            if not c.get("complete", True):
                continue
            mid = c["mid"]
            candles.append(
                Candle(
                    symbol=symbol,
                    timeframe=timeframe,
                    timestamp=datetime.fromisoformat(c["time"].replace("Z", "+00:00")),
                    open=float(mid["o"]),
                    high=float(mid["h"]),
                    low=float(mid["l"]),
                    close=float(mid["c"]),
                    volume=int(c.get("volume", 0)),
                )
            )
        return candles

    def _fetch_prices_sync(self) -> dict[str, float]:
        url = f"{self.BASE_URL}/accounts/{self._account_id}/pricing?instruments=EUR_USD,GBP_USD,XAU_USD"
        headers = {"Authorization": f"Bearer {self._api_key}"}
        data = http_get_json(url, self.name, headers=headers)
        prices: dict[str, float] = {}
        for p in data.get("prices", []):
            inst = p.get("instrument", "").replace("_", "")
            bids = p.get("bids", [])
            asks = p.get("asks", [])
            if bids and asks:
                prices[inst] = (float(bids[0]["price"]) + float(asks[0]["price"])) / 2
        return prices

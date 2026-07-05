"""MetaTrader 5 provider — requires active bridge; no silent fallback."""

from datetime import datetime
from typing import AsyncGenerator

from shared.types.models import Candle, Tick, Timeframe

from .exceptions import MarketDataProviderError
from .provider import MarketDataProvider


class MT5Provider(MarketDataProvider):
    name = "mt5"

    def __init__(self):
        self._connected = False

    async def connect(self) -> bool:
        self._connected = False
        return self._connected

    async def get_candles(
        self, symbol: str, timeframe: Timeframe, count: int = 200
    ) -> list[Candle]:
        if not self._connected:
            raise MarketDataProviderError(
                self.name,
                "MT5 bridge not connected — set MT5_ENABLED=true and configure bridge",
                symbol=symbol,
                timeframe=timeframe.value,
            )
        raise NotImplementedError("MT5 bridge not configured")

    async def get_historical_candles(
        self, symbol: str, timeframe: Timeframe, start: datetime, end: datetime
    ) -> list[Candle]:
        return await self.get_candles(symbol, timeframe, 200)

    async def stream_ticks(self, symbols: list[str]) -> AsyncGenerator[Tick, None]:
        raise MarketDataProviderError(self.name, "MT5 tick stream not configured")

    async def get_live_prices(self) -> dict[str, float]:
        raise MarketDataProviderError(self.name, "MT5 live prices not configured")

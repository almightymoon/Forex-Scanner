"""MetaTrader 5 provider stub — swap in when MT5 bridge is available."""

from datetime import datetime
from typing import AsyncGenerator

from shared.types.models import Candle, Tick, Timeframe

from .frankfurter_provider import FrankfurterProvider
from .provider import MarketDataProvider


class MT5Provider(MarketDataProvider):
    """
    MT5 integration placeholder.
    Set MT5_ENABLED=true and wire the bridge process to replace the fallback.
    """

    name = "mt5"

    def __init__(self):
        self._fallback = FrankfurterProvider()
        self._connected = False

    async def connect(self) -> bool:
        # Bridge hook: import MetaTrader5, initialize(), etc.
        self._connected = False
        return self._connected

    async def get_candles(
        self, symbol: str, timeframe: Timeframe, count: int = 200
    ) -> list[Candle]:
        if self._connected:
            raise NotImplementedError("MT5 bridge not configured")
        return await self._fallback.get_candles(symbol, timeframe, count)

    async def get_historical_candles(
        self, symbol: str, timeframe: Timeframe, start: datetime, end: datetime
    ) -> list[Candle]:
        if hasattr(self._fallback, "get_historical_candles"):
            return await self._fallback.get_historical_candles(symbol, timeframe, start, end)
        return await self.get_candles(symbol, timeframe, 200)

    async def stream_ticks(self, symbols: list[str]) -> AsyncGenerator[Tick, None]:
        async for tick in self._fallback.stream_ticks(symbols):
            yield tick

    async def get_live_prices(self) -> dict[str, float]:
        return await self._fallback.get_live_prices()

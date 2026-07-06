"""MetaTrader 5 provider — disabled; reserved for future broker layer."""

from datetime import datetime
from typing import AsyncGenerator

from services.market_data_service.exceptions import MarketDataProviderError
from services.market_data_service.provider import MarketDataProvider
from shared.types.models import Candle, Tick, Timeframe


class MT5Provider(MarketDataProvider):
    """MT5 broker bridge stub — not registered in the active market-data factory."""

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
                "MT5 bridge not connected — configure broker layer (Phase 2)",
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

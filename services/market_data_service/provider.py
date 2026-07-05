"""Market data provider interface and shared constants."""

import asyncio
from abc import ABC, abstractmethod
from datetime import datetime
from typing import AsyncGenerator, Optional

from shared.types.models import Candle, Tick, Timeframe

FOREX_PAIRS = [
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD",
    "EURGBP", "EURJPY", "GBPJPY", "EURCHF", "EURAUD", "EURCAD", "EURNZD",
    "GBPCHF", "GBPAUD", "GBPCAD", "GBPNZD", "AUDJPY", "AUDCHF", "AUDCAD",
    "AUDNZD", "CADJPY", "CHFJPY", "NZDJPY", "NZDCAD",
    "XAUUSD", "XAGUSD",
]

METAL_PAIRS = ["XAUUSD", "XAGUSD"]

SYMBOL_CATEGORIES = {
    **{s: "major" for s in FOREX_PAIRS[:7]},
    **{s: "metal" for s in METAL_PAIRS},
}

BASE_PRICES = {
    "EURUSD": 1.0875, "GBPUSD": 1.2650, "USDJPY": 149.50, "USDCHF": 0.8820,
    "AUDUSD": 0.6580, "USDCAD": 1.3580, "NZDUSD": 0.6120, "EURGBP": 0.8600,
    "EURJPY": 162.50, "GBPJPY": 189.00, "XAUUSD": 2320.50, "XAGUSD": 27.85,
}


class MarketDataProvider(ABC):
    """Swap providers without changing the scanner."""

    name: str = "base"

    @abstractmethod
    async def get_candles(
        self, symbol: str, timeframe: Timeframe, count: int = 200
    ) -> list[Candle]:
        ...

    async def get_historical_candles(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> list[Candle]:
        candles = await self.get_candles(symbol, timeframe, 500)
        return [c for c in candles if start <= c.timestamp <= end]

    async def stream_ticks(self, symbols: list[str]) -> AsyncGenerator[Tick, None]:
        while True:
            await asyncio.sleep(60)
            yield Tick(symbol=symbols[0] if symbols else "EURUSD", timestamp=datetime.utcnow(), bid=1.0, ask=1.0001)

    async def get_live_prices(self) -> dict[str, float]:
        return {}


# Backward compatibility
from .simulated_provider import SimulatedProvider as SimulatedMarketData
from .tick_processor import TickProcessor as CandleAggregator

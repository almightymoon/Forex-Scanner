"""Simulated market data for development and offline fallback."""

import asyncio
import random
from datetime import datetime, timezone
from typing import AsyncGenerator

from shared.types.models import Candle, Tick, Timeframe

from .candle_builder import generate_candles
from .provider import BASE_PRICES, MarketDataProvider


class SimulatedProvider(MarketDataProvider):
    name = "simulated"

    def __init__(self):
        self._prices = dict(BASE_PRICES)
        self._candle_cache: dict[str, list[Candle]] = {}

    async def get_candles(
        self, symbol: str, timeframe: Timeframe, count: int = 200
    ) -> list[Candle]:
        cache_key = f"{symbol}_{timeframe.value}"
        if cache_key not in self._candle_cache:
            base = self._prices.get(symbol, 1.0)
            self._candle_cache[cache_key] = generate_candles(symbol, timeframe, count, base)
            if self._candle_cache[cache_key]:
                self._prices[symbol] = self._candle_cache[cache_key][-1].close
        return self._candle_cache[cache_key]

    async def stream_ticks(self, symbols: list[str]) -> AsyncGenerator[Tick, None]:
        while True:
            for symbol in symbols:
                price = self._prices.get(symbol, 1.0)
                spread = 0.00015 if "JPY" not in symbol else 0.015
                change = random.gauss(0, price * 0.0001)
                self._prices[symbol] = price + change
                yield Tick(
                    symbol=symbol,
                    timestamp=datetime.now(timezone.utc),
                    bid=round(price, 5),
                    ask=round(price + spread, 5),
                )
            await asyncio.sleep(1)

    async def get_live_prices(self) -> dict[str, float]:
        return dict(self._prices)

"""Market data ingestion and candle management."""

import asyncio
import random
from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator, Optional

from shared.types.models import Candle, Tick, Timeframe


FOREX_PAIRS = [
    # Majors
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD",
    # Minors
    "EURGBP", "EURJPY", "GBPJPY", "EURCHF", "EURAUD", "EURCAD", "EURNZD",
    "GBPCHF", "GBPAUD", "GBPCAD", "GBPNZD", "AUDJPY", "AUDCHF", "AUDCAD",
    "AUDNZD", "CADJPY", "CHFJPY", "NZDJPY", "NZDCAD",
    # Metals — Gold vs USD featured
    "XAUUSD", "XAGUSD",
]

METAL_PAIRS = ["XAUUSD", "XAGUSD"]

SYMBOL_LABELS = {
    "EURUSD": "Euro / US Dollar",
    "GBPUSD": "British Pound / US Dollar",
    "USDJPY": "US Dollar / Japanese Yen",
    "USDCHF": "US Dollar / Swiss Franc",
    "AUDUSD": "Australian Dollar / US Dollar",
    "USDCAD": "US Dollar / Canadian Dollar",
    "NZDUSD": "New Zealand Dollar / US Dollar",
    "EURGBP": "Euro / British Pound",
    "EURJPY": "Euro / Japanese Yen",
    "GBPJPY": "British Pound / Japanese Yen",
    "EURCHF": "Euro / Swiss Franc",
    "EURAUD": "Euro / Australian Dollar",
    "EURCAD": "Euro / Canadian Dollar",
    "EURNZD": "Euro / New Zealand Dollar",
    "GBPCHF": "British Pound / Swiss Franc",
    "GBPAUD": "British Pound / Australian Dollar",
    "GBPCAD": "British Pound / Canadian Dollar",
    "GBPNZD": "British Pound / New Zealand Dollar",
    "AUDJPY": "Australian Dollar / Japanese Yen",
    "AUDCHF": "Australian Dollar / Swiss Franc",
    "AUDCAD": "Australian Dollar / Canadian Dollar",
    "AUDNZD": "Australian Dollar / New Zealand Dollar",
    "CADJPY": "Canadian Dollar / Japanese Yen",
    "CHFJPY": "Swiss Franc / Japanese Yen",
    "NZDJPY": "New Zealand Dollar / Japanese Yen",
    "NZDCAD": "New Zealand Dollar / Canadian Dollar",
    "XAUUSD": "Gold / US Dollar",
    "XAGUSD": "Silver / US Dollar",
}

SYMBOL_CATEGORIES = {
    **{s: "major" for s in FOREX_PAIRS[:7]},
    **{s: "metal" for s in METAL_PAIRS},
}

BASE_PRICES = {
    "EURUSD": 1.0875, "GBPUSD": 1.2650, "USDJPY": 149.50, "USDCHF": 0.8820,
    "AUDUSD": 0.6580, "USDCAD": 1.3580, "NZDUSD": 0.6120, "EURGBP": 0.8600,
    "EURJPY": 162.50, "GBPJPY": 189.00, "XAUUSD": 2320.50, "XAGUSD": 27.85,
}


class MarketDataProvider:
    """Abstract market data provider interface."""

    async def get_candles(
        self, symbol: str, timeframe: Timeframe, count: int = 200
    ) -> list[Candle]:
        raise NotImplementedError

    async def stream_ticks(self, symbols: list[str]) -> AsyncGenerator[Tick, None]:
        raise NotImplementedError


class SimulatedMarketData(MarketDataProvider):
    """Simulated market data for development and testing."""

    def __init__(self):
        self._prices = dict(BASE_PRICES)
        self._candle_cache: dict[str, list[Candle]] = {}

    async def get_candles(
        self, symbol: str, timeframe: Timeframe, count: int = 200
    ) -> list[Candle]:
        cache_key = f"{symbol}_{timeframe.value}"
        if cache_key not in self._candle_cache:
            self._candle_cache[cache_key] = self._generate_candles(symbol, timeframe, count)
        return self._candle_cache[cache_key]

    def _generate_candles(
        self, symbol: str, timeframe: Timeframe, count: int
    ) -> list[Candle]:
        base = self._prices.get(symbol, 1.0)
        tf_minutes = {
            Timeframe.M1: 1, Timeframe.M5: 5, Timeframe.M15: 15,
            Timeframe.M30: 30, Timeframe.H1: 60, Timeframe.H4: 240,
            Timeframe.D1: 1440,
        }
        minutes = tf_minutes.get(timeframe, 60)
        now = datetime.now(timezone.utc)
        candles: list[Candle] = []
        price = base

        for i in range(count, 0, -1):
            ts = now - timedelta(minutes=minutes * i)
            volatility = base * 0.0008 if "JPY" not in symbol else base * 0.0005
            if symbol.startswith("XAU"):
                volatility = base * 0.002
            change = random.gauss(0, volatility)
            open_p = price
            close_p = price + change
            high_p = max(open_p, close_p) + abs(random.gauss(0, volatility * 0.5))
            low_p = min(open_p, close_p) - abs(random.gauss(0, volatility * 0.5))
            vol = random.randint(100, 5000)

            candles.append(
                Candle(
                    symbol=symbol,
                    timeframe=timeframe,
                    timestamp=ts,
                    open=round(open_p, 5),
                    high=round(high_p, 5),
                    low=round(low_p, 5),
                    close=round(close_p, 5),
                    volume=vol,
                    tick_volume=vol * 3,
                    spread=0.00015,
                )
            )
            price = close_p

        self._prices[symbol] = price
        return candles

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


class CandleAggregator:
    """Aggregates ticks into OHLCV candles."""

    def __init__(self, timeframe: Timeframe):
        self.timeframe = timeframe
        self._current: dict[str, Candle] = {}

    def process_tick(self, tick: Tick) -> Optional[Candle]:
        symbol = tick.symbol
        mid = (tick.bid + tick.ask) / 2

        if symbol not in self._current:
            self._current[symbol] = Candle(
                symbol=symbol,
                timeframe=self.timeframe,
                timestamp=tick.timestamp,
                open=mid,
                high=mid,
                low=mid,
                close=mid,
                volume=tick.volume,
            )
            return None

        candle = self._current[symbol]
        candle.high = max(candle.high, mid)
        candle.low = min(candle.low, mid)
        candle.close = mid
        candle.volume += tick.volume
        return None

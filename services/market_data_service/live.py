"""Live market data — real rates with simulated candle history."""

import asyncio
import json
import random
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator, Optional

from shared.configs.settings import get_settings
from shared.types.models import Candle, Tick, Timeframe

from .provider import BASE_PRICES, FOREX_PAIRS, MarketDataProvider, SimulatedMarketData
from .catalog import CATALOG

settings = get_settings()

# Maps symbol to (base, quote) for rate lookup — defaults + catalog
PAIR_CURRENCIES: dict[str, tuple[str, str]] = {
    sym: (e.base, e.quote) for sym, e in CATALOG.items()
}


class LiveMarketData(MarketDataProvider):
    """
    Fetches live spot rates from Frankfurter (ECB) API.
    Builds candle history anchored to real current prices.
    Falls back to simulated data when offline or for metals.
    """

    FRANKFURTER_URL = "https://api.frankfurter.app/latest"

    def __init__(self):
        self._sim = SimulatedMarketData()
        self._live_rates: dict[str, float] = {}
        self._last_fetch: Optional[datetime] = None
        self._candle_cache: dict[str, list[Candle]] = {}

    async def _fetch_live_rates(self) -> dict[str, float]:
        """Fetch EUR-based rates from Frankfurter and derive all pairs."""
        if self._last_fetch and (datetime.now(timezone.utc) - self._last_fetch).seconds < 300:
            return self._live_rates

        try:
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, self._http_get, self.FRANKFURTER_URL)
            rates: dict[str, float] = data.get("rates", {})
            rates["EUR"] = 1.0

            derived: dict[str, float] = {}
            for symbol, (base, quote) in PAIR_CURRENCIES.items():
                if base in ("XAU", "XAG", "XPT", "XPD", "WTI", "BRENT", "BTC", "ETH"):
                    continue
                if symbol in ("USOIL", "UKOIL"):
                    continue
                base_rate = rates.get(base)
                quote_rate = rates.get(quote)
                if base_rate and quote_rate:
                    if base == "EUR":
                        derived[symbol] = quote_rate
                    elif quote == "EUR":
                        derived[symbol] = 1.0 / base_rate
                    else:
                        derived[symbol] = quote_rate / base_rate

            if derived:
                self._live_rates = derived
                self._last_fetch = datetime.now(timezone.utc)

            await self._fetch_metals_prices()
        except Exception:
            pass

        return self._live_rates

    async def _fetch_metals_prices(self):
        """Fetch live Gold (XAU/USD) and Silver from Swissquote public feed."""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            gold_data = await loop.run_in_executor(
                None, self._http_get_raw,
                "https://forex-data-feed.swissquote.com/public-quotes/bboquotes/instrument/XAU/USD",
            )
            quotes = json.loads(gold_data)
            if quotes and quotes[0].get("spreadProfilePrices"):
                mid = quotes[0]["spreadProfilePrices"][0]
                bid, ask = mid.get("bid"), mid.get("ask")
                if bid and ask:
                    self._live_rates["XAUUSD"] = round((bid + ask) / 2, 2)
        except Exception:
            pass

        try:
            loop = asyncio.get_event_loop()
            silver_data = await loop.run_in_executor(
                None, self._http_get_raw,
                "https://forex-data-feed.swissquote.com/public-quotes/bboquotes/instrument/XAG/USD",
            )
            quotes = json.loads(silver_data)
            if quotes and quotes[0].get("spreadProfilePrices"):
                mid = quotes[0]["spreadProfilePrices"][0]
                bid, ask = mid.get("bid"), mid.get("ask")
                if bid and ask:
                    self._live_rates["XAGUSD"] = round((bid + ask) / 2, 3)
        except Exception:
            pass

    @staticmethod
    def _http_get_raw(url: str) -> str:
        req = urllib.request.Request(url, headers={"User-Agent": "FXNavigators/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.read().decode()

    @staticmethod
    def _http_get(url: str) -> dict:
        req = urllib.request.Request(url, headers={"User-Agent": "FXNavigators/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())

    def _anchor_price(self, symbol: str) -> float:
        return self._live_rates.get(symbol) or BASE_PRICES.get(symbol, 1.0)

    async def get_candles(
        self, symbol: str, timeframe: Timeframe, count: int = 200
    ) -> list[Candle]:
        await self._fetch_live_rates()
        cache_key = f"{symbol}_{timeframe.value}"

        live_price = self._anchor_price(symbol)
        if cache_key not in self._candle_cache:
            self._candle_cache[cache_key] = self._build_anchored_candles(
                symbol, timeframe, count, live_price
            )
        else:
            candles = self._candle_cache[cache_key]
            if candles:
                candles[-1] = self._update_last_candle(candles[-1], live_price)

        return self._candle_cache[cache_key]

    def _build_anchored_candles(
        self, symbol: str, timeframe: Timeframe, count: int, anchor: float
    ) -> list[Candle]:
        """Generate realistic history ending at the live anchor price."""
        tf_minutes = {
            Timeframe.M1: 1, Timeframe.M5: 5, Timeframe.M15: 15,
            Timeframe.M30: 30, Timeframe.H1: 60, Timeframe.H4: 240,
            Timeframe.D1: 1440,
        }
        minutes = tf_minutes.get(timeframe, 60)
        now = datetime.now(timezone.utc)
        candles: list[Candle] = []
        price = anchor * (1 + random.gauss(0, 0.002))

        volatility = anchor * 0.0008
        if "JPY" in symbol:
            volatility = anchor * 0.0005
        if symbol.startswith("XAU"):
            volatility = anchor * 0.002

        for i in range(count, 0, -1):
            ts = now - timedelta(minutes=minutes * i)
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

        # Snap last candle to live price
        if candles:
            last = candles[-1]
            candles[-1] = Candle(
                symbol=last.symbol,
                timeframe=last.timeframe,
                timestamp=last.timestamp,
                open=last.open,
                high=max(last.high, anchor),
                low=min(last.low, anchor),
                close=round(anchor, 5),
                volume=last.volume,
                tick_volume=last.tick_volume,
                spread=last.spread,
            )
        return candles

    def _update_last_candle(self, candle: Candle, live_price: float) -> Candle:
        return Candle(
            symbol=candle.symbol,
            timeframe=candle.timeframe,
            timestamp=candle.timestamp,
            open=candle.open,
            high=max(candle.high, live_price),
            low=min(candle.low, live_price),
            close=round(live_price, 5),
            volume=candle.volume,
            tick_volume=candle.tick_volume,
            spread=candle.spread,
        )

    async def stream_ticks(self, symbols: list[str]) -> AsyncGenerator[Tick, None]:
        while True:
            await self._fetch_live_rates()
            for symbol in symbols:
                price = self._anchor_price(symbol)
                spread = 0.00015 if "JPY" not in symbol else 0.015
                yield Tick(
                    symbol=symbol,
                    timestamp=datetime.now(timezone.utc),
                    bid=round(price, 5),
                    ask=round(price + spread, 5),
                )
            await asyncio.sleep(5)

    async def get_live_prices(self) -> dict[str, float]:
        await self._fetch_live_rates()
        return dict(self._live_rates)


def create_market_data_provider() -> MarketDataProvider:
    """Factory: use Twelve Data if key set, else live Frankfurter, else simulated."""
    if settings.TWELVE_DATA_API_KEY:
        from .twelve_data import TwelveDataProvider
        return TwelveDataProvider()
    return LiveMarketData()

"""Frankfurter (ECB) live rates + Swissquote metals — default production provider."""

import asyncio
import json
import random
import urllib.request
from datetime import datetime, timezone
from typing import AsyncGenerator, Optional

from shared.types.models import Candle, Tick, Timeframe

from .candle_builder import generate_candles, update_last_candle
from .catalog import CATALOG
from .provider import BASE_PRICES, MarketDataProvider
from .simulated_provider import SimulatedProvider

PAIR_CURRENCIES: dict[str, tuple[str, str]] = {
    sym: (e.base, e.quote) for sym, e in CATALOG.items()
}


class FrankfurterProvider(MarketDataProvider):
    """Fetches live spot rates from Frankfurter API; metals from Swissquote."""

    name = "frankfurter"
    FRANKFURTER_URL = "https://api.frankfurter.app/latest"

    def __init__(self):
        self._fallback = SimulatedProvider()
        self._live_rates: dict[str, float] = {}
        self._last_fetch: Optional[datetime] = None
        self._candle_cache: dict[str, list[Candle]] = {}

    async def _fetch_live_rates(self) -> dict[str, float]:
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

    async def _fetch_metals_prices(self) -> None:
        for metal, path in (("XAUUSD", "XAU/USD"), ("XAGUSD", "XAG/USD")):
            try:
                loop = asyncio.get_event_loop()
                raw = await loop.run_in_executor(
                    None,
                    self._http_get_raw,
                    f"https://forex-data-feed.swissquote.com/public-quotes/bboquotes/instrument/{path}",
                )
                quotes = json.loads(raw)
                if quotes and quotes[0].get("spreadProfilePrices"):
                    mid = quotes[0]["spreadProfilePrices"][0]
                    bid, ask = mid.get("bid"), mid.get("ask")
                    if bid and ask:
                        self._live_rates[metal] = round((bid + ask) / 2, 2 if metal == "XAUUSD" else 3)
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
            start = live_price * (1 + random.gauss(0, 0.002))
            self._candle_cache[cache_key] = generate_candles(
                symbol, timeframe, count, start, anchor_price=live_price
            )
        elif self._candle_cache[cache_key]:
            candles = self._candle_cache[cache_key]
            candles[-1] = update_last_candle(candles[-1], live_price)

        return self._candle_cache[cache_key]

    async def get_historical_candles(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> list[Candle]:
        """Replay-oriented history — uses anchored synthetic bars until TimescaleDB ingestion."""
        count = max(50, int((end - start).total_seconds() / 3600))
        candles = await self.get_candles(symbol, timeframe, min(count, 500))
        return [c for c in candles if start <= c.timestamp <= end]

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

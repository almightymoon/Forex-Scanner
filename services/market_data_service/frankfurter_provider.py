"""Frankfurter live spot rates — synthetic OHLC only in simulated/development mode."""

import asyncio
import logging
import random
from datetime import datetime, timezone
from typing import AsyncGenerator, Optional

from shared.config.market import is_simulated_mode
from shared.types.models import Candle, Tick, Timeframe

from .candle_builder import generate_candles, update_last_candle
from .catalog import CATALOG
from .exceptions import MarketDataProviderError
from .http_client import http_get_json
from .provider import BASE_PRICES, MarketDataProvider

logger = logging.getLogger("fxnav.market_data")

PAIR_CURRENCIES: dict[str, tuple[str, str]] = {
    sym: (e.base, e.quote) for sym, e in CATALOG.items()
}


class FrankfurterProvider(MarketDataProvider):
    """Live ECB spot rates; OHLC candles only when simulated mode is enabled."""

    name = "frankfurter"
    FRANKFURTER_URL = "https://api.frankfurter.app/latest"

    def __init__(self):
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
        except Exception as exc:
            logger.warning(
                "Frankfurter live rate fetch failed | reason=%s",
                exc,
                exc_info=True,
            )

        return self._live_rates

    async def _fetch_metals_prices(self) -> None:
        import json
        import urllib.request

        for metal, path in (("XAUUSD", "XAU/USD"), ("XAGUSD", "XAG/USD")):
            try:
                url = f"https://forex-data-feed.swissquote.com/public-quotes/bboquotes/instrument/{path}"
                req = urllib.request.Request(url, headers={"User-Agent": "FXNavigators/1.0"})
                loop = asyncio.get_event_loop()
                raw = await loop.run_in_executor(
                    None,
                    lambda u=url, r=req: urllib.request.urlopen(r, timeout=10).read().decode(),
                )
                quotes = json.loads(raw)
                if quotes and quotes[0].get("spreadProfilePrices"):
                    mid = quotes[0]["spreadProfilePrices"][0]
                    bid, ask = mid.get("bid"), mid.get("ask")
                    if bid and ask:
                        self._live_rates[metal] = round((bid + ask) / 2, 2 if metal == "XAUUSD" else 3)
            except Exception as exc:
                logger.warning(
                    "Metals price fetch failed | symbol=%s reason=%s",
                    metal,
                    exc,
                    exc_info=True,
                )

    def _http_get(self, url: str) -> dict:
        return http_get_json(url, self.name)

    def _anchor_price(self, symbol: str) -> float:
        return self._live_rates.get(symbol) or BASE_PRICES.get(symbol, 1.0)

    async def get_candles(
        self, symbol: str, timeframe: Timeframe, count: int = 200
    ) -> list[Candle]:
        if not is_simulated_mode():
            raise MarketDataProviderError(
                self.name,
                "Frankfurter does not provide real historical OHLC — configure TWELVE_DATA_API_KEY "
                "or set ENABLE_SIMULATED_DATA=true for development",
                symbol=symbol,
                timeframe=timeframe.value,
            )

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

        logger.debug("Frankfurter synthetic candles | symbol=%s simulated=true", symbol)
        return self._candle_cache[cache_key]

    async def get_historical_candles(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> list[Candle]:
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

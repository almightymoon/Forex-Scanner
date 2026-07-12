"""Dukascopy HTTP client — historical tick download and candle aggregation."""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from services.data_collector.config import get_collector_config
from services.data_collector.models import RawCandle
from services.data_collector.providers.dukascopy.bi5 import parse_bi5_ticks, ticks_to_candles
from services.data_collector.normalizer import DataNormalizer
from shared.types.models import Timeframe

# Dukascopy uses 0-indexed months in URLs
INSTRUMENT_MAP: dict[str, str] = {
    "EURUSD": "EURUSD",
    "GBPUSD": "GBPUSD",
    "GBPJPY": "GBPJPY",
    "USDJPY": "USDJPY",
    "USDCHF": "USDCHF",
    "USDCAD": "USDCAD",
    "AUDUSD": "AUDUSD",
    "NZDUSD": "NZDUSD",
    "EURJPY": "EURJPY",
    "EURGBP": "EURGBP",
    "XAUUSD": "XAUUSD",
    "XAGUSD": "XAGUSD",
    "BTCUSD": "BTCUSD",
    "ETHUSD": "ETHUSD",
    "NAS100": "USA500IDXUSD",
    "US30": "USA30IDXUSD",
    "SPX500": "USA500IDXUSD",
    "GER40": "DEUIDXEUR",
}

TF_SECONDS = {
    "M1": 60, "M5": 300, "M15": 900, "M30": 1800,
    "H1": 3600, "H4": 14400, "D1": 86400,
}


class DukascopyClient:
    """Download historical ticks from Dukascopy datafeed and aggregate to candles."""

    BASE_URL = "https://datafeed.dukascopy.com/datafeed"

    def __init__(self, timeout: Optional[int] = None):
        cfg = get_collector_config().providers.dukascopy
        self.timeout = timeout or cfg.timeout_seconds

    def map_symbol(self, symbol: str) -> str:
        sym = symbol.upper().replace("/", "")
        return INSTRUMENT_MAP.get(sym, sym)

    async def fetch_candles(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> list[RawCandle]:
        return await asyncio.to_thread(self._fetch_candles_sync, symbol, timeframe, start, end)

    def _fetch_candles_sync(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> list[RawCandle]:
        instrument = self.map_symbol(symbol)
        interval = TF_SECONDS.get(timeframe.value, 3600)
        start_utc = start.astimezone(timezone.utc) if start.tzinfo else start.replace(tzinfo=timezone.utc)
        end_utc = end.astimezone(timezone.utc) if end.tzinfo else end.replace(tzinfo=timezone.utc)

        all_ticks: list[tuple[datetime, float, float, float]] = []
        current = start_utc.replace(minute=0, second=0, microsecond=0)

        while current <= end_utc:
            url = (
                f"{self.BASE_URL}/{instrument}/"
                f"{current.year}/{current.month - 1}/{current.day}/"
                f"{current.hour}h_ticks.bi5"
            )
            try:
                req = Request(url, headers={"User-Agent": "FXNavigators-Collector/1.0"})
                with urlopen(req, timeout=self.timeout) as resp:
                    data = resp.read()
                ticks = parse_bi5_ticks(data, current, symbol)
                all_ticks.extend(ticks)
            except (HTTPError, URLError, TimeoutError):
                pass
            current += timedelta(hours=1)

        candle_dicts = ticks_to_candles(all_ticks, interval, symbol=symbol)
        candles: list[RawCandle] = []
        for c in candle_dicts:
            if start_utc <= c["timestamp"] <= end_utc:
                candles.append(RawCandle(
                    symbol=symbol.upper(),
                    timeframe=timeframe.value,
                    timestamp=c["timestamp"],
                    open=c["open"],
                    high=c["high"],
                    low=c["low"],
                    close=c["close"],
                    volume=c["volume"],
                ))
        return candles

    def fetch_ticks_sync(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
    ) -> list[tuple[datetime, float, float, float]]:
        """Download raw ticks (immutable storage source)."""
        instrument = self.map_symbol(symbol)
        start_utc = start.astimezone(timezone.utc) if start.tzinfo else start.replace(tzinfo=timezone.utc)
        end_utc = end.astimezone(timezone.utc) if end.tzinfo else end.replace(tzinfo=timezone.utc)

        all_ticks: list[tuple[datetime, float, float, float]] = []
        current = start_utc.replace(minute=0, second=0, microsecond=0)

        while current <= end_utc:
            url = (
                f"{self.BASE_URL}/{instrument}/"
                f"{current.year}/{current.month - 1}/{current.day}/"
                f"{current.hour}h_ticks.bi5"
            )
            try:
                req = Request(url, headers={"User-Agent": "FXNavigators-Collector/1.0"})
                with urlopen(req, timeout=self.timeout) as resp:
                    data = resp.read()
                ticks = parse_bi5_ticks(data, current, symbol)
                all_ticks.extend(ticks)
            except (HTTPError, URLError, TimeoutError):
                pass
            current += timedelta(hours=1)

        return [(t, b, a, v) for t, b, a, v in all_ticks if start_utc <= t <= end_utc]

    async def fetch_ticks(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
    ) -> list[tuple[datetime, float, float, float]]:
        return await asyncio.to_thread(self.fetch_ticks_sync, symbol, start, end)

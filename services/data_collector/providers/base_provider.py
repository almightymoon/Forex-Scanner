"""Abstract base class for market data providers."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import AsyncGenerator, Optional

from services.data_collector.models import ProviderHealthStatus, RawCandle, RawTick
from shared.types.models import Timeframe


class BaseDataProvider(ABC):
    """
    Provider interface for the data collector.

    Every provider must implement connect, download_history, stream_live,
    health, and disconnect. New providers can be added without modifying
    collector.py.
    """

    name: str

    @abstractmethod
    async def connect(self) -> bool:
        """Establish connection to the data source."""

    @abstractmethod
    async def download_history(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> list[RawCandle]:
        """Download historical OHLC candles for the given range."""

    @abstractmethod
    async def stream_live(
        self, symbols: list[str]
    ) -> AsyncGenerator[RawTick | RawCandle, None]:
        """Stream live ticks or forming candles. Yields until cancelled."""
        yield  # pragma: no cover — makes this a generator for type checkers

    @abstractmethod
    async def health(self) -> ProviderHealthStatus:
        """Return current provider health metrics."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Cleanly close the connection."""

    def map_symbol(self, symbol: str) -> str:
        """Override to translate internal symbol to provider-native format."""
        return symbol.upper().replace("/", "")

    def map_timeframe(self, timeframe: Timeframe) -> str:
        """Override to translate internal timeframe to provider-native format."""
        return timeframe.value

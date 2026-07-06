"""Mock provider for unit tests."""

from datetime import datetime, timezone
from typing import AsyncGenerator

from services.data_collector.models import ProviderHealthStatus, ProviderState, RawCandle, RawTick
from services.data_collector.providers.base_provider import BaseDataProvider
from shared.types.models import Timeframe


class MockDataProvider(BaseDataProvider):
    name = "mock"

    def __init__(self, candles: list[RawCandle] | None = None):
        self._connected = False
        self._candles = candles or []
        self._rows_collected = 0

    async def connect(self) -> bool:
        self._connected = True
        return True

    async def download_history(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> list[RawCandle]:
        if not self._connected:
            raise ConnectionError("not connected")
        result = [
            c for c in self._candles
            if c.symbol == symbol and start <= c.timestamp <= end
        ]
        self._rows_collected += len(result)
        return result

    async def stream_live(
        self, symbols: list[str]
    ) -> AsyncGenerator[RawTick | RawCandle, None]:
        if not self._connected:
            raise ConnectionError("not connected")
        for sym in symbols:
            yield RawTick(sym, datetime.now(timezone.utc), 1.1, 1.1002)

    async def health(self) -> ProviderHealthStatus:
        return ProviderHealthStatus(
            provider=self.name,
            state=ProviderState.CONNECTED if self._connected else ProviderState.DISCONNECTED,
            connected=self._connected,
            last_update=datetime.now(timezone.utc),
            rows_collected=self._rows_collected,
        )

    async def disconnect(self) -> None:
        self._connected = False

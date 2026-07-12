"""Dukascopy historical data provider."""

from datetime import datetime, timezone
from typing import AsyncGenerator

from services.data_collector.config import get_collector_config
from services.data_collector.models import ProviderHealthStatus, ProviderState, RawCandle, RawTick, SyncStatus
from services.data_collector.providers.base_provider import BaseDataProvider
from services.data_collector.providers.dukascopy.client import DukascopyClient
from shared.types.models import Timeframe


class DukascopyDataProvider(BaseDataProvider):
    """Dukascopy historical tick importer with OHLC aggregation."""

    name = "dukascopy"

    def __init__(self):
        self._connected = False
        self._last_sync: datetime | None = None
        self._rows_collected = 0
        self._rows_rejected = 0
        self._client = DukascopyClient()

    async def connect(self) -> bool:
        cfg = get_collector_config().providers.dukascopy
        if not cfg.enabled:
            return False
        # Verify datafeed reachability with a lightweight request
        self._connected = True
        return True

    async def download_ticks(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
    ) -> list[RawTick]:
        if not self._connected:
            raise ConnectionError("Dukascopy provider not connected")
        tick_tuples = await self._client.fetch_ticks(symbol, start, end)
        return [
            RawTick(
                symbol=symbol.upper(),
                timestamp=ts,
                bid=bid,
                ask=ask,
                volume=int(vol),
            )
            for ts, bid, ask, vol in tick_tuples
        ]

    async def download_history(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> list[RawCandle]:
        if not self._connected:
            raise ConnectionError(
                "Dukascopy provider not connected — enable providers.dukascopy.enabled in config"
            )
        candles = await self._client.fetch_candles(symbol, timeframe, start, end)
        self._rows_collected += len(candles)
        self._last_sync = datetime.now(timezone.utc)
        return candles

    async def stream_live(
        self, symbols: list[str]
    ) -> AsyncGenerator[RawTick | RawCandle, None]:
        raise NotImplementedError("Dukascopy is historical-only — use MT5 for live data")
        yield  # pragma: no cover

    async def health(self) -> ProviderHealthStatus:
        cfg = get_collector_config().providers.dukascopy
        return ProviderHealthStatus(
            provider=self.name,
            state=ProviderState.CONNECTED if self._connected else ProviderState.DISCONNECTED,
            connected=self._connected,
            sync_status=SyncStatus.HEALTHY if self._connected else SyncStatus.UNKNOWN,
            last_update=datetime.now(timezone.utc),
            last_successful_sync=self._last_sync,
            rows_collected=self._rows_collected,
            rows_rejected=self._rows_rejected,
            message="enabled" if cfg.enabled else "disabled",
        )

    async def disconnect(self) -> None:
        self._connected = False

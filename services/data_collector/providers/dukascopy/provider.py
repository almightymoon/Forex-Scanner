"""Dukascopy data provider stub for Milestone 3."""

from datetime import datetime, timezone
from typing import AsyncGenerator

from services.data_collector.config import get_collector_config
from services.data_collector.models import ProviderHealthStatus, ProviderState, RawCandle, RawTick
from services.data_collector.providers.base_provider import BaseDataProvider
from shared.types.models import Timeframe


class DukascopyDataProvider(BaseDataProvider):
    """
    Dukascopy historical tick/candle importer.

    Milestone 1: interface-compliant stub.
    Milestone 3: implement bi5 tick download + candle aggregation.
    """

    name = "dukascopy"

    def __init__(self):
        self._connected = False
        self._last_sync: datetime | None = None
        self._rows_collected = 0
        self._rows_rejected = 0

    async def connect(self) -> bool:
        cfg = get_collector_config().providers.dukascopy
        if not cfg.enabled:
            return False
        # Milestone 3: verify datafeed endpoint reachability
        self._connected = False
        return self._connected

    async def download_history(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> list[RawCandle]:
        if not self._connected:
            raise ConnectionError(
                f"Dukascopy provider not connected — enable in config/data_collector.yaml "
                f"(providers.dukascopy.enabled) and complete Milestone 3 integration"
            )
        # Milestone 3: download .bi5 tick files, aggregate to OHLC
        return []

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
            last_update=datetime.now(timezone.utc),
            last_successful_sync=self._last_sync,
            rows_collected=self._rows_collected,
            rows_rejected=self._rows_rejected,
            message="enabled" if cfg.enabled else "disabled — Milestone 3",
        )

    async def disconnect(self) -> None:
        self._connected = False

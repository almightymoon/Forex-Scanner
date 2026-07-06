"""MT5 data provider stub for Milestone 2."""

from datetime import datetime, timezone
from typing import AsyncGenerator

from services.data_collector.config import get_collector_config
from services.data_collector.models import ProviderHealthStatus, ProviderState, RawCandle, RawTick
from services.data_collector.providers.base_provider import BaseDataProvider
from shared.types.models import Timeframe


class MT5DataProvider(BaseDataProvider):
    """
    MetaTrader 5 bridge.

    Milestone 1: interface-compliant stub.
    Milestone 2: wire MetaTrader5 Python package + terminal connection.
    """

    name = "mt5"

    def __init__(self):
        self._connected = False
        self._last_sync: datetime | None = None
        self._rows_collected = 0
        self._rows_rejected = 0

    async def connect(self) -> bool:
        cfg = get_collector_config().providers.mt5
        if not cfg.enabled:
            return False
        # Milestone 2: import MetaTrader5; mt5.initialize(...)
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
                f"MT5 provider not connected — enable in config/data_collector.yaml "
                f"(providers.mt5.enabled) and complete Milestone 2 integration"
            )
        # Milestone 2: mt5.copy_rates_range(...)
        return []

    async def stream_live(
        self, symbols: list[str]
    ) -> AsyncGenerator[RawTick | RawCandle, None]:
        if not self._connected:
            raise ConnectionError("MT5 provider not connected")
        # Milestone 2: poll mt5.symbol_info_tick in a loop
        return
        yield  # pragma: no cover

    async def health(self) -> ProviderHealthStatus:
        cfg = get_collector_config().providers.mt5
        return ProviderHealthStatus(
            provider=self.name,
            state=ProviderState.CONNECTED if self._connected else ProviderState.DISCONNECTED,
            connected=self._connected,
            last_update=datetime.now(timezone.utc),
            last_successful_sync=self._last_sync,
            rows_collected=self._rows_collected,
            rows_rejected=self._rows_rejected,
            message="enabled" if cfg.enabled else "disabled — Milestone 2",
        )

    async def disconnect(self) -> None:
        # Milestone 2: mt5.shutdown()
        self._connected = False

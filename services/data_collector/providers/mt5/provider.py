"""MetaTrader 5 data provider."""

import asyncio
from datetime import datetime, timezone
from typing import AsyncGenerator, Optional

from services.data_collector.config import get_collector_config
from services.data_collector.models import ProviderHealthStatus, ProviderState, RawCandle, RawTick, SyncStatus
from services.data_collector.providers.base_provider import BaseDataProvider
from shared.types.models import Timeframe

try:
    import MetaTrader5 as mt5
    _MT5_AVAILABLE = True
except ImportError:
    mt5 = None  # type: ignore
    _MT5_AVAILABLE = False

MT5_TF_MAP: dict[str, int] = {}


def _build_tf_map() -> dict[str, int]:
    if not _MT5_AVAILABLE:
        return {}
    return {
        "M1": mt5.TIMEFRAME_M1,
        "M5": mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15,
        "M30": mt5.TIMEFRAME_M30,
        "H1": mt5.TIMEFRAME_H1,
        "H4": mt5.TIMEFRAME_H4,
        "D1": mt5.TIMEFRAME_D1,
    }


class MT5DataProvider(BaseDataProvider):
    """MetaTrader 5 bridge via the official MetaTrader5 Python package."""

    name = "mt5"

    def __init__(self):
        self._connected = False
        self._last_sync: datetime | None = None
        self._rows_collected = 0
        self._rows_rejected = 0
        self._tf_map = _build_tf_map()

    async def connect(self) -> bool:
        cfg = get_collector_config().providers.mt5
        if not cfg.enabled:
            return False
        if not _MT5_AVAILABLE:
            return False
        return await asyncio.to_thread(self._connect_sync, cfg)

    def _connect_sync(self, cfg) -> bool:
        assert mt5 is not None
        kwargs = {}
        if cfg.host and cfg.host != "localhost":
            kwargs["host"] = cfg.host
        if cfg.port:
            kwargs["port"] = cfg.port
        if not mt5.initialize(**kwargs):
            self._connected = False
            return False
        if cfg.login and cfg.password:
            authorized = mt5.login(cfg.login, password=cfg.password, server=cfg.server or "")
            self._connected = bool(authorized)
            return self._connected
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
            raise ConnectionError("MT5 provider not connected")
        return await asyncio.to_thread(
            self._download_sync, symbol, timeframe, start, end,
        )

    def _download_sync(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> list[RawCandle]:
        assert mt5 is not None
        mt5_tf = self._tf_map.get(timeframe.value)
        if mt5_tf is None:
            raise ValueError(f"Unsupported MT5 timeframe: {timeframe.value}")

        sym = self.map_symbol(symbol)
        if not mt5.symbol_select(sym, True):
            raise ConnectionError(f"MT5 symbol not available: {sym}")

        start_utc = start.astimezone(timezone.utc) if start.tzinfo else start.replace(tzinfo=timezone.utc)
        end_utc = end.astimezone(timezone.utc) if end.tzinfo else end.replace(tzinfo=timezone.utc)

        rates = mt5.copy_rates_range(sym, mt5_tf, start_utc, end_utc)
        if rates is None:
            err = mt5.last_error()
            raise ConnectionError(f"MT5 copy_rates_range failed: {err}")

        candles: list[RawCandle] = []
        for r in rates:
            ts = datetime.fromtimestamp(int(r["time"]), tz=timezone.utc)
            candles.append(RawCandle(
                symbol=sym,
                timeframe=timeframe.value,
                timestamp=ts,
                open=float(r["open"]),
                high=float(r["high"]),
                low=float(r["low"]),
                close=float(r["close"]),
                volume=int(r["tick_volume"]),
            ))
        self._rows_collected += len(candles)
        self._last_sync = datetime.now(timezone.utc)
        return candles

    async def stream_live(
        self, symbols: list[str]
    ) -> AsyncGenerator[RawTick | RawCandle, None]:
        if not self._connected or not _MT5_AVAILABLE:
            raise ConnectionError("MT5 provider not connected")
        while True:
            for sym in symbols:
                tick = await asyncio.to_thread(self._last_tick, sym)
                if tick:
                    yield tick
            await asyncio.sleep(1)

    def _last_tick(self, symbol: str) -> Optional[RawTick]:
        assert mt5 is not None
        sym = self.map_symbol(symbol)
        info = mt5.symbol_info_tick(sym)
        if info is None:
            return None
        return RawTick(
            symbol=sym,
            timestamp=datetime.fromtimestamp(info.time, tz=timezone.utc),
            bid=float(info.bid),
            ask=float(info.ask),
            volume=int(info.volume),
        )

    async def health(self) -> ProviderHealthStatus:
        cfg = get_collector_config().providers.mt5
        if not cfg.enabled:
            return ProviderHealthStatus(
                provider=self.name,
                state=ProviderState.DISCONNECTED,
                connected=False,
                sync_status=SyncStatus.UNKNOWN,
                message="disabled",
            )
        if not _MT5_AVAILABLE:
            return ProviderHealthStatus(
                provider=self.name,
                state=ProviderState.ERROR,
                connected=False,
                sync_status=SyncStatus.OFFLINE,
                message="MetaTrader5 package not installed",
            )
        return ProviderHealthStatus(
            provider=self.name,
            state=ProviderState.CONNECTED if self._connected else ProviderState.DISCONNECTED,
            connected=self._connected,
            sync_status=SyncStatus.HEALTHY if self._connected else SyncStatus.OFFLINE,
            last_update=datetime.now(timezone.utc),
            last_successful_sync=self._last_sync,
            rows_collected=self._rows_collected,
            rows_rejected=self._rows_rejected,
            message="connected" if self._connected else "not connected — is MT5 terminal running?",
        )

    async def disconnect(self) -> None:
        if _MT5_AVAILABLE and mt5 is not None:
            await asyncio.to_thread(mt5.shutdown)
        self._connected = False

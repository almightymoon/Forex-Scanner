"""Internal market data read service — cache + database, no direct provider access."""

from datetime import datetime, timezone
from typing import Any, Optional

from services.data_collector.cache import MarketDataCache, get_market_cache
from services.data_collector.config import get_collector_config
from services.data_collector.database import CollectorDatabase, get_collector_database
from services.data_collector.metrics import CollectorMetrics, get_collector_metrics
from services.data_collector.models import DataGap, ProviderHealthStatus
from services.data_collector.symbols import SymbolRegistry
from shared.types.models import Timeframe


def _candle_dict(candle) -> dict[str, Any]:
    return {
        "symbol": candle.symbol,
        "timeframe": candle.timeframe.value if hasattr(candle.timeframe, "value") else candle.timeframe,
        "timestamp": candle.timestamp.isoformat() if isinstance(candle.timestamp, datetime) else candle.timestamp,
        "open": candle.open,
        "high": candle.high,
        "low": candle.low,
        "close": candle.close,
        "volume": candle.volume,
        "provider": candle.provider,
    }


class InternalMarketDataService:
    """
    Read-only market data facade for the internal API.

    Scanner consumers should use this service — never provider implementations.
    """

    def __init__(
        self,
        database: Optional[CollectorDatabase] = None,
        cache: Optional[MarketDataCache] = None,
        metrics: Optional[CollectorMetrics] = None,
    ):
        self.database = database or get_collector_database()
        self.cache = cache or get_market_cache()
        self.metrics = metrics or get_collector_metrics()
        self.registry = SymbolRegistry()
        self.config = get_collector_config()

    def get_candles(
        self,
        symbol: str,
        timeframe: Timeframe,
        *,
        limit: int = 200,
        since: Optional[datetime] = None,
    ) -> list[dict[str, Any]]:
        sym = symbol.upper()
        tf = timeframe.value

        if self.config.cache.enabled:
            cached = self.cache.get_candles(sym, tf)
            if cached and not since:
                return cached[:limit]

        candles = self.database.get_candles(sym, timeframe, limit=limit, since=since)
        payload = [_candle_dict(c) for c in candles]

        if self.config.cache.enabled and payload:
            self.cache.set_candles(sym, tf, payload)
            self.cache.set_latest_candle(sym, tf, payload[-1])

        return payload

    def get_latest(self, symbol: str, timeframe: Timeframe) -> Optional[dict[str, Any]]:
        sym = symbol.upper()
        tf = timeframe.value

        if self.config.cache.enabled:
            cached = self.cache.get_latest_candle(sym, tf)
            if cached:
                return cached

        candles = self.database.get_candles(sym, timeframe, limit=1)
        if not candles:
            return None
        latest = _candle_dict(candles[-1])
        if self.config.cache.enabled:
            self.cache.set_latest_candle(sym, tf, latest)
        return latest

    def get_symbols(self) -> list[dict[str, Any]]:
        return [
            {
                "symbol": s.symbol,
                "name": s.name,
                "category": s.category,
                "base_currency": s.base_currency,
                "quote_currency": s.quote_currency,
                "is_active": s.is_active,
            }
            for s in self.registry.all()
        ]

    def get_status(self) -> dict[str, Any]:
        providers = self.database.get_all_provider_statuses()
        open_gaps = self.database.get_open_gaps(limit=1000)
        return {
            "healthy": all(
                p.sync_status.value == "healthy" or p.message.startswith("disabled")
                for p in providers
            ) if providers else True,
            "candle_count": self.database.count_candles(),
            "open_gaps": len(open_gaps),
            "providers_online": sum(1 for p in providers if p.connected),
            "metrics": self.metrics.snapshot(),
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    def get_gaps(
        self,
        symbol: Optional[str] = None,
        timeframe: Optional[Timeframe] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        gaps = self.database.get_open_gaps(symbol, timeframe, limit=limit)
        return [self._gap_dict(g) for g in gaps]

    def get_providers(self) -> list[dict[str, Any]]:
        statuses = self.database.get_all_provider_statuses()
        result = []
        for s in statuses:
            payload = self._provider_dict(s)
            if self.config.cache.enabled:
                self.cache.set_provider_health(s.provider, payload)
            result.append(payload)
        return result

    def get_metrics_prometheus(self) -> str:
        return self.metrics.export_prometheus()

    @staticmethod
    def _gap_dict(gap: DataGap) -> dict[str, Any]:
        return {
            "id": gap.id,
            "symbol": gap.symbol,
            "timeframe": gap.timeframe.value,
            "gap_type": gap.gap_type.value,
            "expected_timestamp": gap.expected_timestamp.isoformat() if gap.expected_timestamp else None,
            "gap_start": gap.gap_start.isoformat() if gap.gap_start else None,
            "gap_end": gap.gap_end.isoformat() if gap.gap_end else None,
            "status": gap.status.value,
            "provider": gap.provider,
            "created_at": gap.created_at.isoformat() if gap.created_at else None,
        }

    @staticmethod
    def _provider_dict(status: ProviderHealthStatus) -> dict[str, Any]:
        return {
            "provider": status.provider,
            "state": status.state.value,
            "sync_status": status.sync_status.value,
            "connected": status.connected,
            "last_update": status.last_update.isoformat() if status.last_update else None,
            "last_successful_sync": status.last_successful_sync.isoformat() if status.last_successful_sync else None,
            "last_candle_timestamp": status.last_candle_timestamp.isoformat() if status.last_candle_timestamp else None,
            "rows_collected": status.rows_collected,
            "rows_downloaded": status.rows_downloaded,
            "rows_rejected": status.rows_rejected,
            "rows_repaired": status.rows_repaired,
            "latency_ms": status.latency_ms,
            "sync_latency_ms": status.sync_latency_ms,
            "message": status.message,
        }


_service: Optional[InternalMarketDataService] = None


def get_market_data_service() -> InternalMarketDataService:
    global _service
    if _service is None:
        _service = InternalMarketDataService()
    return _service

def reset_market_data_service() -> None:
    global _service
    _service = None

"""Provider synchronization — track sync state, latency, and health classification."""

import time
from datetime import datetime, timezone
from typing import Optional

from services.data_collector.models import ProviderHealthStatus, ProviderState, SyncStatus
from services.data_collector.providers.base_provider import BaseDataProvider
from shared.types.models import Timeframe


class ProviderSynchronizer:
    """Track and persist per-provider synchronization metrics."""

    def __init__(self, database):
        self.database = database

    async def sync_provider(
        self,
        provider: BaseDataProvider,
        *,
        rows_downloaded: int = 0,
        rows_rejected: int = 0,
        rows_repaired: int = 0,
        last_candle: Optional[datetime] = None,
        error: Optional[Exception] = None,
    ) -> ProviderHealthStatus:
        t0 = time.perf_counter()
        try:
            base_status = await provider.health()
            latency_ms = (time.perf_counter() - t0) * 1000
            sync_status = self._classify_status(base_status, error)
            now = datetime.now(timezone.utc)

            existing = self.database.get_provider_status(provider.name)
            rows_collected = (existing.rows_collected if existing else 0) + rows_downloaded
            total_rejected = (existing.rows_rejected if existing else 0) + rows_rejected
            total_repaired = (existing.rows_repaired if existing else 0) + rows_repaired

            status = ProviderHealthStatus(
                provider=provider.name,
                state=base_status.state,
                connected=base_status.connected and sync_status == SyncStatus.HEALTHY,
                sync_status=sync_status,
                last_update=now,
                last_successful_sync=now if not error else (existing.last_successful_sync if existing else None),
                last_candle_timestamp=last_candle or (existing.last_candle_timestamp if existing else None),
                rows_collected=rows_collected,
                rows_downloaded=rows_downloaded,
                rows_rejected=total_rejected,
                rows_repaired=total_repaired,
                latency_ms=latency_ms,
                sync_latency_ms=latency_ms,
                message=base_status.message if not error else str(error),
            )
            self.database.update_provider_status(status)
            return status

        except Exception as exc:
            return await self.sync_provider(
                provider,
                rows_downloaded=rows_downloaded,
                rows_rejected=rows_rejected,
                rows_repaired=rows_repaired,
                last_candle=last_candle,
                error=exc,
            )

    def record_sync(
        self,
        provider_name: str,
        *,
        rows_downloaded: int = 0,
        rows_rejected: int = 0,
        rows_repaired: int = 0,
        last_candle: Optional[datetime] = None,
        sync_latency_ms: Optional[float] = None,
        sync_status: SyncStatus = SyncStatus.HEALTHY,
        message: str = "",
    ) -> ProviderHealthStatus:
        existing = self.database.get_provider_status(provider_name)
        now = datetime.now(timezone.utc)
        status = ProviderHealthStatus(
            provider=provider_name,
            state=ProviderState.CONNECTED if sync_status == SyncStatus.HEALTHY else ProviderState.DEGRADED,
            connected=sync_status == SyncStatus.HEALTHY,
            sync_status=sync_status,
            last_update=now,
            last_successful_sync=now if sync_status == SyncStatus.HEALTHY else (
                existing.last_successful_sync if existing else None
            ),
            last_candle_timestamp=last_candle or (existing.last_candle_timestamp if existing else None),
            rows_collected=(existing.rows_collected if existing else 0) + rows_downloaded,
            rows_downloaded=rows_downloaded,
            rows_rejected=(existing.rows_rejected if existing else 0) + rows_rejected,
            rows_repaired=(existing.rows_repaired if existing else 0) + rows_repaired,
            latency_ms=sync_latency_ms,
            sync_latency_ms=sync_latency_ms,
            message=message,
        )
        self.database.update_provider_status(status)
        return status

    @staticmethod
    def _classify_status(status: ProviderHealthStatus, error: Optional[Exception]) -> SyncStatus:
        if error:
            msg = str(error).lower()
            if "401" in msg or "auth" in msg or "unauthorized" in msg:
                return SyncStatus.AUTHENTICATION_FAILED
            if "429" in msg or "rate" in msg:
                return SyncStatus.RATE_LIMITED
            if "connect" in msg or "offline" in msg or "timeout" in msg:
                return SyncStatus.OFFLINE
            return SyncStatus.OFFLINE

        if status.connected and status.state in (ProviderState.CONNECTED,):
            return SyncStatus.HEALTHY
        if status.state == ProviderState.DEGRADED:
            return SyncStatus.RATE_LIMITED
        if not status.connected:
            return SyncStatus.OFFLINE
        return SyncStatus.UNKNOWN

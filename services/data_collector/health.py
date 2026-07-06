"""Health reporting for the market data collector."""

from datetime import datetime, timezone
from typing import Any, Optional

from services.data_collector.database import CollectorDatabase, get_collector_database
from services.data_collector.models import ProviderHealthStatus
from services.data_collector.providers.base_provider import BaseDataProvider


class CollectorHealth:
    """Aggregate provider and collection health metrics."""

    def __init__(
        self,
        database: Optional[CollectorDatabase] = None,
        providers: Optional[list[BaseDataProvider]] = None,
    ):
        self.database = database or get_collector_database()
        self.providers = providers or []

    async def refresh_provider_health(self) -> list[ProviderHealthStatus]:
        statuses = []
        for provider in self.providers:
            status = await provider.health()
            self.database.update_provider_status(status)
            statuses.append(status)
        return statuses

    def get_provider_statuses(self) -> list[ProviderHealthStatus]:
        return self.database.get_all_provider_statuses()

    def get_provider_status(self, provider: str) -> Optional[ProviderHealthStatus]:
        return self.database.get_provider_status(provider)

    def snapshot(self) -> dict[str, Any]:
        """Full health snapshot for API / monitoring."""
        statuses = self.get_provider_statuses()
        return {
            "status": "healthy" if all(s.connected or s.message.startswith("disabled") for s in statuses) else "degraded",
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "providers": [
                {
                    "provider": s.provider,
                    "state": s.state.value,
                    "connected": s.connected,
                    "last_update": s.last_update.isoformat() if s.last_update else None,
                    "last_successful_sync": s.last_successful_sync.isoformat() if s.last_successful_sync else None,
                    "rows_collected": s.rows_collected,
                    "rows_rejected": s.rows_rejected,
                    "latency_ms": s.latency_ms,
                    "message": s.message,
                }
                for s in statuses
            ],
        }

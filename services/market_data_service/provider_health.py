"""Provider health tracking — last success, failure, latency."""

from dataclasses import dataclass
from datetime import datetime, timezone
from threading import RLock

from .exceptions import ProviderStatus


@dataclass
class ProviderHealthRecord:
    provider_name: str
    status: ProviderStatus = ProviderStatus.UNAVAILABLE
    last_success: datetime | None = None
    last_failure: datetime | None = None
    latency_ms: float | None = None
    last_error: str | None = None
    fallback_used: bool = False

    def to_dict(self) -> dict:
        return {
            "provider_name": self.provider_name,
            "provider_status": self.status.value,
            "last_success": self.last_success.isoformat() if self.last_success else None,
            "last_failure": self.last_failure.isoformat() if self.last_failure else None,
            "latency_ms": round(self.latency_ms, 1) if self.latency_ms is not None else None,
            "last_error": self.last_error,
            "fallback_used": self.fallback_used,
        }


class ProviderHealthTracker:
    _lock = RLock()
    _records: dict[str, ProviderHealthRecord] = {}

    @classmethod
    def _record(cls, provider_name: str) -> ProviderHealthRecord:
        if provider_name not in cls._records:
            cls._records[provider_name] = ProviderHealthRecord(provider_name=provider_name)
        return cls._records[provider_name]

    @classmethod
    def get(cls, provider_name: str) -> ProviderHealthRecord:
        with cls._lock:
            return cls._record(provider_name)

    @classmethod
    def record_success(cls, provider_name: str, latency_ms: float) -> None:
        with cls._lock:
            rec = cls._record(provider_name)
            rec.status = ProviderStatus.HEALTHY
            rec.last_success = datetime.now(timezone.utc)
            rec.latency_ms = latency_ms
            rec.last_error = None
            rec.fallback_used = False

    @classmethod
    def record_failure(
        cls,
        provider_name: str,
        status: ProviderStatus,
        error: str,
        latency_ms: float | None = None,
        fallback_used: bool = False,
    ) -> None:
        with cls._lock:
            rec = cls._record(provider_name)
            rec.status = status
            rec.last_failure = datetime.now(timezone.utc)
            rec.last_error = error
            if latency_ms is not None:
                rec.latency_ms = latency_ms
            rec.fallback_used = fallback_used

    @classmethod
    def snapshot(cls, provider_name: str | None = None) -> dict:
        with cls._lock:
            if provider_name:
                return cls._record(provider_name).to_dict()
            return {name: rec.to_dict() for name, rec in cls._records.items()}

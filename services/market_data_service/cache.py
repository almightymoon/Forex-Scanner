"""In-memory TTL cache for candles and live prices."""

from datetime import datetime, timedelta, timezone
from typing import Any, Optional


class MarketDataCache:
    def __init__(self, ttl_seconds: int = 300):
        self.ttl = timedelta(seconds=ttl_seconds)
        self._store: dict[str, tuple[Any, datetime]] = {}

    def get(self, key: str) -> Optional[Any]:
        entry = self._store.get(key)
        if not entry:
            return None
        value, ts = entry
        if datetime.now(timezone.utc) - ts > self.ttl:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any) -> None:
        self._store[key] = (value, datetime.now(timezone.utc))

    def invalidate(self, key: str) -> None:
        self._store.pop(key, None)

    def clear(self) -> None:
        self._store.clear()

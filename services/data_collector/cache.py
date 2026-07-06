"""Optional Redis cache with PostgreSQL fallback for market data reads."""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from shared.configs.settings import get_settings

logger = logging.getLogger("data_collector.cache")

CACHE_TTL_SECONDS = 60
CANDLE_CACHE_TTL = 300


class MarketDataCache:
    """
    Cache latest candles, ticks, and provider health in Redis.

    Falls back to database-only reads when Redis is unavailable.
    """

    def __init__(self, redis_url: Optional[str] = None):
        settings = get_settings()
        self.redis_url = redis_url or settings.REDIS_URL
        self._client = None
        self._available = False
        self._connect()

    def _connect(self) -> None:
        try:
            import redis
            client = redis.from_url(self.redis_url, socket_connect_timeout=1, decode_responses=True)
            client.ping()
            self._client = client
            self._available = True
        except Exception as exc:
            self._client = None
            self._available = False
            logger.debug("Redis unavailable, using database fallback: %s", exc)

    @property
    def available(self) -> bool:
        return self._available and self._client is not None

    def _key(self, *parts: str) -> str:
        return "fxnav:market:" + ":".join(parts)

    def get_candles(self, symbol: str, timeframe: str) -> Optional[list[dict]]:
        if not self.available:
            return None
        try:
            raw = self._client.get(self._key("candles", symbol, timeframe))
            return json.loads(raw) if raw else None
        except Exception:
            return None

    def set_candles(self, symbol: str, timeframe: str, candles: list[dict], ttl: int = CANDLE_CACHE_TTL) -> None:
        if not self.available:
            return
        try:
            self._client.setex(
                self._key("candles", symbol, timeframe),
                ttl,
                json.dumps(candles, default=str),
            )
        except Exception:
            pass

    def get_latest_candle(self, symbol: str, timeframe: str) -> Optional[dict]:
        if not self.available:
            return None
        try:
            raw = self._client.get(self._key("latest", symbol, timeframe))
            return json.loads(raw) if raw else None
        except Exception:
            return None

    def set_latest_candle(self, symbol: str, timeframe: str, candle: dict) -> None:
        if not self.available:
            return
        try:
            self._client.setex(
                self._key("latest", symbol, timeframe),
                CACHE_TTL_SECONDS,
                json.dumps(candle, default=str),
            )
        except Exception:
            pass

    def get_latest_tick(self, symbol: str) -> Optional[dict]:
        if not self.available:
            return None
        try:
            raw = self._client.get(self._key("tick", symbol))
            return json.loads(raw) if raw else None
        except Exception:
            return None

    def set_latest_tick(self, symbol: str, tick: dict) -> None:
        if not self.available:
            return
        try:
            self._client.setex(self._key("tick", symbol), CACHE_TTL_SECONDS, json.dumps(tick, default=str))
        except Exception:
            pass

    def get_provider_health(self, provider: str) -> Optional[dict]:
        if not self.available:
            return None
        try:
            raw = self._client.get(self._key("provider", provider))
            return json.loads(raw) if raw else None
        except Exception:
            return None

    def set_provider_health(self, provider: str, status: dict) -> None:
        if not self.available:
            return
        try:
            self._client.setex(
                self._key("provider", provider),
                CACHE_TTL_SECONDS,
                json.dumps(status, default=str),
            )
        except Exception:
            pass

    def invalidate_candles(self, symbol: str, timeframe: str) -> None:
        if not self.available:
            return
        try:
            self._client.delete(self._key("candles", symbol, timeframe))
            self._client.delete(self._key("latest", symbol, timeframe))
        except Exception:
            pass


_cache: Optional[MarketDataCache] = None


def get_market_cache() -> MarketDataCache:
    global _cache
    if _cache is None:
        _cache = MarketDataCache()
    return _cache

def reset_market_cache() -> None:
    global _cache
    _cache = None

"""Market data configuration."""

from dataclasses import dataclass
from functools import lru_cache
import os


@dataclass(frozen=True)
class MarketConfig:
    provider: str = "frankfurter"
    cache_ttl_seconds: int = 300
    candle_default_count: int = 200
    tick_stream_interval: float = 5.0
    twelve_data_api_key: str = ""
    polygon_api_key: str = ""
    mt5_enabled: bool = False
    reconnect_max_attempts: int = 5
    reconnect_backoff_seconds: float = 2.0


@lru_cache
def get_market_config() -> MarketConfig:
    return MarketConfig(
        provider=os.getenv("MARKET_DATA_PROVIDER", "frankfurter"),
        cache_ttl_seconds=int(os.getenv("MARKET_CACHE_TTL", "300")),
        twelve_data_api_key=os.getenv("TWELVE_DATA_API_KEY", ""),
        polygon_api_key=os.getenv("POLYGON_API_KEY", ""),
        mt5_enabled=os.getenv("MT5_ENABLED", "").lower() == "true",
    )

"""Market data configuration — loaded from config/market.yaml + environment."""

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "market.yaml"


@dataclass(frozen=True)
class ProviderConfig:
    default: str = "twelvedata"
    simulated_enabled: bool = False
    fallback_enabled: bool = False
    retry_count: int = 3


@dataclass(frozen=True)
class MarketConfig:
    provider: ProviderConfig
    timeout: int = 10
    cache_ttl_seconds: int = 300
    candle_default_count: int = 200
    real_ohlc_providers: tuple[str, ...] = ("twelvedata", "polygon", "oanda", "mt5")

    @property
    def simulated_mode(self) -> bool:
        if self.provider.simulated_enabled:
            return True
        if os.getenv("ENABLE_SIMULATED_DATA", "").lower() == "true":
            return True
        if os.getenv("ENVIRONMENT", "").lower() == "development":
            return True
        return False


def _load_yaml() -> dict[str, Any]:
    if not _CONFIG_PATH.exists():
        return {}
    with open(_CONFIG_PATH) as f:
        return yaml.safe_load(f) or {}


def _env_bool(name: str, yaml_default: bool) -> bool:
    val = os.getenv(name)
    if val is not None:
        return val.lower() == "true"
    return bool(yaml_default)


@lru_cache
def get_market_config() -> MarketConfig:
    raw = _load_yaml()
    p = raw.get("provider", {})
    return MarketConfig(
        provider=ProviderConfig(
            default=os.getenv("MARKET_DATA_PROVIDER", p.get("default", "twelvedata")).lower(),
            simulated_enabled=_env_bool("ENABLE_SIMULATED_DATA", p.get("simulated_enabled", False)),
            fallback_enabled=p.get("fallback_enabled", False),
            retry_count=int(p.get("retry_count", 3)),
        ),
        timeout=int(raw.get("timeout", 10)),
        cache_ttl_seconds=int(os.getenv("MARKET_CACHE_TTL", "300")),
    )


def is_simulated_mode() -> bool:
    return get_market_config().simulated_mode

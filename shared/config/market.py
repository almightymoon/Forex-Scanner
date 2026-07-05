"""Market data configuration — loaded from config/market.yaml + explicit env flags."""

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
    allow_fallback: bool = False
    retry_count: int = 3

    @property
    def fallback_enabled(self) -> bool:
        """Backward-compatible alias."""
        return self.allow_fallback


@dataclass(frozen=True)
class MarketConfig:
    provider: ProviderConfig
    timeout: int = 10
    cache_ttl_seconds: int = 300
    candle_default_count: int = 200
    real_ohlc_providers: tuple[str, ...] = ("twelvedata", "polygon", "oanda", "mt5")

    @property
    def simulated_mode(self) -> bool:
        """Simulation is opt-in only — never inferred from ENVIRONMENT."""
        return self.provider.simulated_enabled


def _load_yaml() -> dict[str, Any]:
    if not _CONFIG_PATH.exists():
        return {}
    with open(_CONFIG_PATH) as f:
        return yaml.safe_load(f) or {}


def _explicit_simulated_flag() -> bool:
    """Only ENABLE_SIMULATED_DATA=true opts in via environment (explicit string)."""
    return os.getenv("ENABLE_SIMULATED_DATA", "").lower() == "true"


@lru_cache
def get_market_config() -> MarketConfig:
    raw = _load_yaml()
    p = raw.get("provider", {})
    yaml_sim = bool(p.get("simulated_enabled", False))
    env_sim = _explicit_simulated_flag()
    allow_fallback = bool(p.get("allow_fallback", p.get("fallback_enabled", False)))

    return MarketConfig(
        provider=ProviderConfig(
            default=os.getenv("MARKET_DATA_PROVIDER", p.get("default", "twelvedata")).lower(),
            simulated_enabled=yaml_sim or env_sim,
            allow_fallback=allow_fallback,
            retry_count=int(p.get("retry_count", 3)),
        ),
        timeout=int(raw.get("timeout", 10)),
        cache_ttl_seconds=int(os.getenv("MARKET_CACHE_TTL", "300")),
    )


def is_simulated_mode() -> bool:
    return get_market_config().simulated_mode


def reload_market_config() -> MarketConfig:
    get_market_config.cache_clear()
    return get_market_config()

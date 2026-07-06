"""Market data configuration — loaded from config/market.yaml + explicit env flags."""

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "market.yaml"

ACTIVE_OHLC_PROVIDERS = ("twelvedata", "polygon")


@dataclass(frozen=True)
class ProviderConfig:
    default: str = "twelvedata"
    simulated_enabled: bool = False
    allow_fallback: bool = False
    retry_count: int = 3
    active_providers: tuple[str, ...] = ACTIVE_OHLC_PROVIDERS

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


def _parse_provider_block(raw: dict[str, Any]) -> ProviderConfig:
    """Support new market_data block and legacy provider block."""
    md = raw.get("market_data", {})
    legacy = raw.get("provider", {})

    default = md.get("default_provider", legacy.get("default", "twelvedata"))
    yaml_sim = bool(md.get("simulated_enabled", legacy.get("simulated_enabled", False)))
    allow_fallback = bool(
        md.get("fallback_enabled", legacy.get("allow_fallback", legacy.get("fallback_enabled", False)))
    )
    retry_count = int(md.get("retry_count", legacy.get("retry_count", 3)))

    providers_raw = md.get("providers", list(ACTIVE_OHLC_PROVIDERS))
    active = tuple(p.lower() for p in providers_raw if p.lower() in ACTIVE_OHLC_PROVIDERS)
    if not active:
        active = ACTIVE_OHLC_PROVIDERS

    return ProviderConfig(
        default=os.getenv("MARKET_DATA_PROVIDER", default).lower(),
        simulated_enabled=yaml_sim or _explicit_simulated_flag(),
        allow_fallback=allow_fallback,
        retry_count=retry_count,
        active_providers=active,
    )


@lru_cache
def get_market_config() -> MarketConfig:
    raw = _load_yaml()
    return MarketConfig(
        provider=_parse_provider_block(raw),
        timeout=int(raw.get("timeout", 10)),
        cache_ttl_seconds=int(os.getenv("MARKET_CACHE_TTL", "300")),
    )


def is_simulated_mode() -> bool:
    return get_market_config().simulated_mode


def reload_market_config() -> MarketConfig:
    get_market_config.cache_clear()
    return get_market_config()

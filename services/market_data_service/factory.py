"""Resolve configured market data provider — Twelve Data → Polygon → Simulated."""

import importlib
import logging
import os

from shared.config.market import get_market_config, is_simulated_mode

from .exceptions import MarketDataProviderError, ProviderAuthError
from .provider import MarketDataProvider
from .provider_chain import ProviderChain
from .provider_health import ProviderHealthTracker

logger = logging.getLogger("fxnav.market_data")

# Phase 1 — active OHLC providers only
ACTIVE_PROVIDERS = {
    "simulated": "services.market_data_service.simulated_provider.SimulatedProvider",
    "twelvedata": "services.market_data_service.twelvedata_provider.TwelveDataProvider",
    "polygon": "services.market_data_service.polygon_provider.PolygonProvider",
}

# Phase 2 — broker layer (disabled, not registered at runtime)
DISABLED_PROVIDERS = {
    "oanda": "services.market_data_service.providers.disabled.oanda_provider.OandaProvider",
    "mt5": "services.market_data_service.providers.disabled.mt5_provider.MT5Provider",
}

PROVIDER_PRIORITY = ("twelvedata", "polygon")


def _import_class(path: str):
    module_path, class_name = path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def _has_api_key(key: str) -> bool:
    if key == "twelvedata":
        return bool(os.getenv("TWELVE_DATA_API_KEY", ""))
    if key == "polygon":
        return bool(os.getenv("POLYGON_API_KEY", ""))
    return False


def _validate_provider_key(key: str) -> None:
    if key == "twelvedata" and not os.getenv("TWELVE_DATA_API_KEY", ""):
        raise ProviderAuthError("twelvedata", "TWELVE_DATA_API_KEY is not configured")
    if key == "polygon" and not os.getenv("POLYGON_API_KEY", ""):
        raise ProviderAuthError("polygon", "POLYGON_API_KEY is not configured")


def validate_startup() -> None:
    """Fail fast when no real provider keys are configured."""
    if is_simulated_mode():
        return

    if not _has_api_key("twelvedata") and not _has_api_key("polygon"):
        raise ProviderAuthError(
            "market_data",
            "Startup failed: configure TWELVE_DATA_API_KEY and/or POLYGON_API_KEY, "
            "or set ENABLE_SIMULATED_DATA=true for development",
        )


def _ordered_provider_keys() -> list[str]:
    """Priority: Twelve Data → Polygon (Polygon as primary only when Twelve Data absent)."""
    cfg = get_market_config()
    has_twelve = _has_api_key("twelvedata")
    has_polygon = _has_api_key("polygon")
    fallback = cfg.provider.fallback_enabled or (has_twelve and has_polygon)

    keys: list[str] = []
    if has_twelve:
        keys.append("twelvedata")
    if has_polygon and (fallback or not has_twelve):
        keys.append("polygon")
    return keys


def _instantiate(key: str) -> MarketDataProvider:
    class_path = ACTIVE_PROVIDERS.get(key)
    if not class_path:
        raise MarketDataProviderError(key, f"Unknown active market data provider: {key}")
    _validate_provider_key(key)
    provider = _import_class(class_path)()
    ProviderHealthTracker.get(provider.name)
    return provider


def create_provider(name: str | None = None) -> MarketDataProvider:
    validate_startup()

    if is_simulated_mode():
        key = (name or "simulated").lower()
        if key != "simulated":
            logger.warning("Simulated mode active — forcing provider=simulated (requested=%s)", key)
        provider = _instantiate("simulated")
        logger.info("Market data provider selected: simulated (explicit dev mode)")
        from .startup import print_startup_banner
        print_startup_banner("simulated")
        return provider

    keys = _ordered_provider_keys()
    if not keys:
        raise ProviderAuthError(
            "market_data",
            "No market data provider configured — set API keys or ENABLE_SIMULATED_DATA=true",
        )

    providers = [_instantiate(k) for k in keys]
    cfg = get_market_config()
    # Auto-enable failover when both providers are configured (Twelve Data free tier
    # cannot sustain full multi-pair scans).
    allow_fallback = len(providers) > 1 and (
        cfg.provider.fallback_enabled
        or (_has_api_key("twelvedata") and _has_api_key("polygon"))
    )

    if len(providers) == 1:
        provider = providers[0]
    else:
        provider = ProviderChain(providers, allow_fallback=allow_fallback)

    active_name = provider.active_provider if isinstance(provider, ProviderChain) else provider.name
    logger.info(
        "Market data provider selected: %s (chain=%s fallback=%s)",
        active_name,
        [p.name for p in providers],
        allow_fallback,
    )

    from .startup import print_startup_banner
    print_startup_banner(active_name)

    return provider


def create_market_data_provider() -> MarketDataProvider:
    from .service import MarketDataService
    return MarketDataService(create_provider())

"""Resolve configured market data provider — no silent fallbacks."""

import logging
import os

from shared.config.market import get_market_config, is_simulated_mode
from shared.configs.settings import get_settings

from .exceptions import MarketDataProviderError, ProviderAuthError
from .provider import MarketDataProvider
from .provider_health import ProviderHealthTracker

logger = logging.getLogger("fxnav.market_data")
settings = get_settings()

PROVIDERS = {
    "simulated": "services.market_data_service.simulated_provider.SimulatedProvider",
    "frankfurter": "services.market_data_service.frankfurter_provider.FrankfurterProvider",
    "twelvedata": "services.market_data_service.twelvedata_provider.TwelveDataProvider",
    "mt5": "services.market_data_service.mt5_provider.MT5Provider",
    "polygon": "services.market_data_service.polygon_provider.PolygonProvider",
    "oanda": "services.market_data_service.oanda_provider.OandaProvider",
}


def _import_class(path: str):
    module_path, class_name = path.rsplit(".", 1)
    import importlib
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def _validate_provider_key(key: str) -> None:
    if key == "twelvedata" and not settings.TWELVE_DATA_API_KEY:
        raise ProviderAuthError("twelvedata", "TWELVE_DATA_API_KEY is not configured")
    if key == "polygon" and not settings.POLYGON_API_KEY:
        raise ProviderAuthError("polygon", "POLYGON_API_KEY is not configured")
    if key == "oanda" and (not settings.OANDA_API_KEY or not settings.OANDA_ACCOUNT_ID):
        raise ProviderAuthError("oanda", "OANDA_API_KEY and OANDA_ACCOUNT_ID are required")
    if key == "mt5" and os.getenv("MT5_ENABLED", "").lower() != "true":
        raise MarketDataProviderError("mt5", "MT5_ENABLED must be true and bridge configured")


def _resolve_provider_key(explicit: str | None = None) -> str:
    if is_simulated_mode():
        key = (explicit or os.getenv("MARKET_DATA_PROVIDER") or "simulated").lower()
        logger.info("Simulated market data mode enabled — provider=%s", key)
        return key

    cfg = get_market_config()
    key = (explicit or cfg.provider.default).lower()
    _validate_provider_key(key)
    return key


def create_provider(name: str | None = None) -> MarketDataProvider:
    key = _resolve_provider_key(name)
    class_path = PROVIDERS.get(key)
    if not class_path:
        raise MarketDataProviderError(key, f"Unknown market data provider: {key}")

    provider = _import_class(class_path)()
    ProviderHealthTracker.get(provider.name)
    logger.info("Market data provider selected: %s", provider.name)

    from .startup import print_startup_banner
    print_startup_banner(provider.name)

    return provider


def create_market_data_provider() -> MarketDataProvider:
    from .service import MarketDataService
    return MarketDataService(create_provider())

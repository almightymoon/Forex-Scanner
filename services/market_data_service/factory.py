"""Provider factory — select data source via MARKET_DATA_PROVIDER env."""

import os

from shared.configs.settings import get_settings

from .provider import MarketDataProvider

settings = get_settings()

PROVIDERS = {
    "simulated": "services.market_data_service.simulated_provider.SimulatedProvider",
    "frankfurter": "services.market_data_service.frankfurter_provider.FrankfurterProvider",
    "twelvedata": "services.market_data_service.twelvedata_provider.TwelveDataProvider",
    "mt5": "services.market_data_service.mt5_provider.MT5Provider",
    "polygon": "services.market_data_service.polygon_provider.PolygonProvider",
}


def _import_class(path: str):
    module_path, class_name = path.rsplit(".", 1)
    import importlib
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def create_provider(name: str | None = None) -> MarketDataProvider:
    """Resolve provider by name or auto-detect from API keys."""
    if name:
        key = name.lower()
    elif settings.TWELVE_DATA_API_KEY:
        key = "twelvedata"
    elif settings.POLYGON_API_KEY:
        key = "polygon"
    elif os.getenv("MT5_ENABLED", "").lower() == "true":
        key = "mt5"
    else:
        key = os.getenv("MARKET_DATA_PROVIDER", "frankfurter").lower()

    class_path = PROVIDERS.get(key, PROVIDERS["frankfurter"])
    cls = _import_class(class_path)
    return cls()


def create_market_data_provider() -> MarketDataProvider:
    """Legacy entry point — returns composed service wrapping the selected provider."""
    from .service import MarketDataService
    return MarketDataService(create_provider())

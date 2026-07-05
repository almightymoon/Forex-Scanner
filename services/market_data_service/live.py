"""Backward-compatible re-exports."""

from .factory import create_market_data_provider, create_provider
from .frankfurter_provider import FrankfurterProvider

# Legacy alias used across the codebase
LiveMarketData = FrankfurterProvider

__all__ = ["LiveMarketData", "create_market_data_provider", "create_provider", "FrankfurterProvider"]

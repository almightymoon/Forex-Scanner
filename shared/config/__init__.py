"""Centralized configuration for FX Navigators."""

from .database import DatabaseConfig, get_database_config
from .market import (
    MarketConfig,
    ProviderConfig,
    SimulatedDataForbiddenError,
    assert_simulated_data_allowed,
    get_market_config,
    get_runtime_environment,
    is_production_environment,
    is_simulated_mode,
)
from .notifications import NotificationsConfig, get_notifications_config
from .scanner import DEFAULT_SCORING, ScannerConfig, ScoringConfig, get_scanner_config
from .scoring_loader import V2ScoringConfig, V2Weights, get_v2_scoring_config

__all__ = [
    "DatabaseConfig",
    "MarketConfig",
    "ProviderConfig",
    "NotificationsConfig",
    "ScannerConfig",
    "ScoringConfig",
    "DEFAULT_SCORING",
    "V2ScoringConfig",
    "V2Weights",
    "SimulatedDataForbiddenError",
    "assert_simulated_data_allowed",
    "get_v2_scoring_config",
    "get_database_config",
    "get_market_config",
    "get_runtime_environment",
    "is_production_environment",
    "is_simulated_mode",
    "get_notifications_config",
    "get_scanner_config",
]

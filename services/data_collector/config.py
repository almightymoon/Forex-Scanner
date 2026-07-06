"""Configuration loader for the market data collector."""

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "data_collector.yaml"

SUPPORTED_TIMEFRAMES = ("M1", "M5", "M15", "M30", "H1", "H4", "D1")


@dataclass(frozen=True)
class DatabaseConfig:
    url: str = ""
    pool_size: int = 5
    auto_migrate: bool = True


@dataclass(frozen=True)
class MT5ProviderConfig:
    enabled: bool = False
    host: str = "localhost"
    port: int = 443
    login: int = 0
    password: str = ""
    server: str = ""
    timeout_seconds: int = 30


@dataclass(frozen=True)
class DukascopyProviderConfig:
    enabled: bool = False
    base_url: str = "https://datafeed.dukascopy.com"
    timeout_seconds: int = 60
    max_concurrent_downloads: int = 4


@dataclass(frozen=True)
class ProvidersConfig:
    mt5: MT5ProviderConfig = field(default_factory=MT5ProviderConfig)
    dukascopy: DukascopyProviderConfig = field(default_factory=DukascopyProviderConfig)


@dataclass(frozen=True)
class SchedulerConfig:
    polling_interval_seconds: int = 60
    incremental_interval_seconds: int = 300
    historical_batch_size: int = 500
    max_concurrent_jobs: int = 3
    retry_count: int = 3
    retry_backoff_seconds: int = 5


@dataclass(frozen=True)
class ValidationConfig:
    max_future_skew_seconds: int = 60
    gap_detection_enabled: bool = True
    reject_duplicates: bool = True


@dataclass(frozen=True)
class LoggingConfig:
    level: str = "INFO"
    json: bool = True


@dataclass(frozen=True)
class CollectorConfig:
    database: DatabaseConfig
    providers: ProvidersConfig
    symbols: tuple[str, ...]
    timeframes: tuple[str, ...]
    scheduler: SchedulerConfig
    validation: ValidationConfig
    logging: LoggingConfig


def _load_yaml() -> dict[str, Any]:
    if not _CONFIG_PATH.exists():
        return {}
    with open(_CONFIG_PATH) as f:
        return yaml.safe_load(f) or {}


def _parse_providers(raw: dict[str, Any]) -> ProvidersConfig:
    mt5_raw = raw.get("mt5", {})
    duka_raw = raw.get("dukascopy", {})
    return ProvidersConfig(
        mt5=MT5ProviderConfig(
            enabled=bool(mt5_raw.get("enabled", False)),
            host=str(mt5_raw.get("host", "localhost")),
            port=int(mt5_raw.get("port", 443)),
            login=int(mt5_raw.get("login", 0)),
            password=str(mt5_raw.get("password", "")),
            server=str(mt5_raw.get("server", "")),
            timeout_seconds=int(mt5_raw.get("timeout_seconds", 30)),
        ),
        dukascopy=DukascopyProviderConfig(
            enabled=bool(duka_raw.get("enabled", False)),
            base_url=str(duka_raw.get("base_url", "https://datafeed.dukascopy.com")),
            timeout_seconds=int(duka_raw.get("timeout_seconds", 60)),
            max_concurrent_downloads=int(duka_raw.get("max_concurrent_downloads", 4)),
        ),
    )


@lru_cache
def get_collector_config() -> CollectorConfig:
    raw = _load_yaml()
    db_raw = raw.get("database", {})
    sched_raw = raw.get("scheduler", {})
    val_raw = raw.get("validation", {})
    log_raw = raw.get("logging", {})

    symbols = tuple(s.upper() for s in raw.get("symbols", []))
    timeframes = tuple(
        tf.upper() for tf in raw.get("timeframes", list(SUPPORTED_TIMEFRAMES))
        if tf.upper() in SUPPORTED_TIMEFRAMES
    )

    return CollectorConfig(
        database=DatabaseConfig(
            url=os.getenv("COLLECTOR_DATABASE_URL", db_raw.get("url", "")),
            pool_size=int(db_raw.get("pool_size", 5)),
            auto_migrate=bool(db_raw.get("auto_migrate", True)),
        ),
        providers=_parse_providers(raw.get("providers", {})),
        symbols=symbols,
        timeframes=timeframes or SUPPORTED_TIMEFRAMES,
        scheduler=SchedulerConfig(
            polling_interval_seconds=int(sched_raw.get("polling_interval_seconds", 60)),
            incremental_interval_seconds=int(sched_raw.get("incremental_interval_seconds", 300)),
            historical_batch_size=int(sched_raw.get("historical_batch_size", 500)),
            max_concurrent_jobs=int(sched_raw.get("max_concurrent_jobs", 3)),
            retry_count=int(sched_raw.get("retry_count", 3)),
            retry_backoff_seconds=int(sched_raw.get("retry_backoff_seconds", 5)),
        ),
        validation=ValidationConfig(
            max_future_skew_seconds=int(val_raw.get("max_future_skew_seconds", 60)),
            gap_detection_enabled=bool(val_raw.get("gap_detection_enabled", True)),
            reject_duplicates=bool(val_raw.get("reject_duplicates", True)),
        ),
        logging=LoggingConfig(
            level=os.getenv("COLLECTOR_LOG_LEVEL", log_raw.get("level", "INFO")),
            json=bool(log_raw.get("json", True)),
        ),
    )


def reload_collector_config() -> CollectorConfig:
    get_collector_config.cache_clear()
    return get_collector_config()

"""Structured logging for the market data collector."""

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Optional

from services.data_collector.config import get_collector_config

_LOGGER: Optional[logging.Logger] = None


class StructuredFormatter(logging.Formatter):
    """Emit JSON log lines for ingestion by observability stacks."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "collector_fields") and isinstance(record.collector_fields, dict):
            payload.update(record.collector_fields)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def get_logger(name: str = "data_collector") -> logging.Logger:
    global _LOGGER
    if _LOGGER is not None:
        return _LOGGER.getChild(name) if name != "data_collector" else _LOGGER

    cfg = get_collector_config()
    logger = logging.getLogger("data_collector")
    logger.setLevel(getattr(logging, cfg.logging.level.upper(), logging.INFO))
    logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    if cfg.logging.json:
        handler.setFormatter(StructuredFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s — %(message)s"))

    logger.addHandler(handler)
    logger.propagate = False
    _LOGGER = logger
    return logger


def log_collection(
    logger: logging.Logger,
    *,
    provider: str,
    symbol: str,
    timeframe: str,
    duration_ms: float,
    rows_imported: int,
    rows_rejected: int = 0,
    level: int = logging.INFO,
    error: Optional[str] = None,
    **extra: Any,
) -> None:
    fields = {
        "provider": provider,
        "symbol": symbol,
        "timeframe": timeframe,
        "duration_ms": round(duration_ms, 2),
        "rows_imported": rows_imported,
        "rows_rejected": rows_rejected,
        **extra,
    }
    if error:
        fields["error"] = error
        level = logging.ERROR

    record = logger.makeRecord(
        logger.name, level, "", 0,
        f"collection {provider}/{symbol}/{timeframe}",
        (), None,
    )
    record.collector_fields = fields
    logger.handle(record)

"""HTTP client with logging, retries, latency tracking, and classified errors."""

import json
import logging
import socket
import time
import urllib.error
import urllib.request
from typing import Any

from shared.config.market import get_market_config

from .exceptions import (
    ProviderAuthError,
    ProviderNetworkError,
    ProviderRateLimitError,
    ProviderStatus,
    ProviderTimeoutError,
)
from .provider_health import ProviderHealthTracker

logger = logging.getLogger("fxnav.market_data")


def http_get_json(
    url: str,
    provider: str,
    *,
    symbol: str | None = None,
    timeframe: str | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Fetch JSON with retries, health tracking, and structured logging."""
    cfg = get_market_config()
    timeout = cfg.timeout
    retries = cfg.provider.retry_count
    hdrs = {"User-Agent": "FXNavigators/1.0", **(headers or {})}
    last_exc: Exception | None = None

    for attempt in range(1, retries + 1):
        start = time.perf_counter()
        try:
            req = urllib.request.Request(url, headers=hdrs)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read())
            latency_ms = (time.perf_counter() - start) * 1000
            ProviderHealthTracker.record_success(provider, latency_ms)
            return data
        except urllib.error.HTTPError as exc:
            latency_ms = (time.perf_counter() - start) * 1000
            body = exc.read().decode(errors="replace")[:500]
            reason = f"{exc.code} {exc.reason}: {body}"
            status, error_cls = _classify_http(exc.code, provider, reason, symbol, timeframe)
            ProviderHealthTracker.record_failure(provider, status, reason, latency_ms)
            _log_failure(
                provider, symbol, timeframe, reason, latency_ms,
                fallback="Disabled", exc_info=exc.code not in (429,),
            )
            last_exc = error_cls(provider, reason, symbol=symbol, timeframe=timeframe)
            if exc.code in (429, 401, 403) or attempt >= retries:
                raise last_exc from exc
        except urllib.error.URLError as exc:
            latency_ms = (time.perf_counter() - start) * 1000
            if isinstance(exc.reason, socket.timeout):
                reason = f"Timeout after {timeout}s"
                status = ProviderStatus.TIMEOUT
                error_cls = ProviderTimeoutError
            else:
                reason = str(exc.reason)
                status = ProviderStatus.NETWORK_ERROR
                error_cls = ProviderNetworkError
            ProviderHealthTracker.record_failure(provider, status, reason, latency_ms)
            _log_failure(provider, symbol, timeframe, reason, latency_ms, fallback="Disabled")
            last_exc = error_cls(provider, reason, symbol=symbol, timeframe=timeframe)
            if attempt >= retries:
                raise last_exc from exc
        except Exception as exc:
            latency_ms = (time.perf_counter() - start) * 1000
            reason = str(exc)
            ProviderHealthTracker.record_failure(provider, ProviderStatus.UNAVAILABLE, reason, latency_ms)
            _log_failure(provider, symbol, timeframe, reason, latency_ms, fallback="Disabled")
            last_exc = exc
            if attempt >= retries:
                raise

    if last_exc:
        raise last_exc
    raise ProviderNetworkError(provider, "Unknown HTTP failure", symbol=symbol, timeframe=timeframe)


def _classify_http(code: int, provider: str, reason: str, symbol, timeframe):
    if code == 429:
        return ProviderStatus.RATE_LIMITED, ProviderRateLimitError
    if code in (401, 403):
        return ProviderStatus.AUTHENTICATION_FAILED, ProviderAuthError
    return ProviderStatus.UNAVAILABLE, ProviderNetworkError


def _log_failure(
    provider: str,
    symbol: str | None,
    timeframe: str | None,
    reason: str,
    latency_ms: float,
    fallback: str,
    exc_info: bool = True,
) -> None:
    logger.warning(
        "%s provider failed | symbol=%s timeframe=%s reason=%s latency_ms=%.1f fallback=%s",
        provider,
        symbol or "-",
        timeframe or "-",
        reason,
        latency_ms,
        fallback,
        exc_info=exc_info,
    )

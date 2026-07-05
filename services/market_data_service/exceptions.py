"""Market data provider errors — never fail silently."""

from enum import Enum


class ProviderStatus(str, Enum):
    HEALTHY = "healthy"
    UNAVAILABLE = "unavailable"
    RATE_LIMITED = "rate_limited"
    AUTHENTICATION_FAILED = "authentication_failed"
    TIMEOUT = "timeout"
    NETWORK_ERROR = "network_error"


class MarketDataProviderError(Exception):
    """Raised when a provider cannot return data and fallback is disabled."""

    def __init__(
        self,
        provider: str,
        message: str,
        status: ProviderStatus = ProviderStatus.UNAVAILABLE,
        symbol: str | None = None,
        timeframe: str | None = None,
        fallback_used: bool = False,
    ):
        self.provider = provider
        self.status = status
        self.symbol = symbol
        self.timeframe = timeframe
        self.fallback_used = fallback_used
        super().__init__(message)


class ProviderRateLimitError(MarketDataProviderError):
    def __init__(self, provider: str, message: str, **kwargs):
        super().__init__(provider, message, status=ProviderStatus.RATE_LIMITED, **kwargs)


class ProviderAuthError(MarketDataProviderError):
    def __init__(self, provider: str, message: str, **kwargs):
        super().__init__(provider, message, status=ProviderStatus.AUTHENTICATION_FAILED, **kwargs)


class ProviderTimeoutError(MarketDataProviderError):
    def __init__(self, provider: str, message: str, **kwargs):
        super().__init__(provider, message, status=ProviderStatus.TIMEOUT, **kwargs)


class ProviderNetworkError(MarketDataProviderError):
    def __init__(self, provider: str, message: str, **kwargs):
        super().__init__(provider, message, status=ProviderStatus.NETWORK_ERROR, **kwargs)

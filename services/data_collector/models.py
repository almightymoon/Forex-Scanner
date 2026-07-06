"""Domain models for the market data collector."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from shared.types.models import Timeframe


class JobType(str, Enum):
    HISTORICAL_IMPORT = "historical_import"
    INCREMENTAL_UPDATE = "incremental_update"
    LIVE_POLL = "live_poll"


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"


class ProviderState(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DEGRADED = "degraded"
    ERROR = "error"


@dataclass
class RawCandle:
    """Provider-native candle before normalization."""

    symbol: str
    timeframe: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RawTick:
    """Provider-native tick before normalization."""

    symbol: str
    timestamp: datetime
    bid: float
    ask: float
    volume: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CollectedCandle:
    """Normalized candle stored in the database."""

    symbol: str
    timeframe: Timeframe
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    provider: str
    created_at: datetime


@dataclass
class CollectedTick:
    """Normalized tick stored in the database."""

    symbol: str
    timestamp: datetime
    bid: float
    ask: float
    volume: int
    provider: str
    created_at: datetime


@dataclass
class ValidationResult:
    valid: list[CollectedCandle]
    rejected: list[tuple[CollectedCandle, str]]
    warnings: list[str]
    gaps_detected: list[tuple[datetime, datetime]]


@dataclass
class ProviderHealthStatus:
    provider: str
    state: ProviderState
    connected: bool
    last_update: Optional[datetime] = None
    last_successful_sync: Optional[datetime] = None
    rows_collected: int = 0
    rows_rejected: int = 0
    latency_ms: Optional[float] = None
    message: str = ""


@dataclass
class CollectionJob:
    id: str
    job_type: JobType
    provider: str
    symbol: str
    timeframe: Timeframe
    status: JobStatus = JobStatus.PENDING
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    rows_imported: int = 0
    rows_rejected: int = 0
    retry_count: int = 0
    error: Optional[str] = None


@dataclass
class CollectionLogEntry:
    provider: str
    symbol: str
    timeframe: str
    job_type: str
    duration_ms: float
    rows_imported: int
    rows_rejected: int
    status: str
    message: str = ""
    created_at: Optional[datetime] = None

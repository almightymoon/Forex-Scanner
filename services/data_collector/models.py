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


class SyncStatus(str, Enum):
    HEALTHY = "healthy"
    RATE_LIMITED = "rate_limited"
    OFFLINE = "offline"
    AUTHENTICATION_FAILED = "authentication_failed"
    UNKNOWN = "unknown"


class GapType(str, Enum):
    MISSING = "missing"
    DUPLICATE = "duplicate"
    TIMESTAMP_GAP = "timestamp_gap"
    OVERLAP = "overlap"
    OUT_OF_ORDER = "out_of_order"


class GapStatus(str, Enum):
    OPEN = "open"
    REPAIRED = "repaired"
    UNRESOLVED = "unresolved"


class HistoricalRange(str, Enum):
    ONE_MONTH = "1m"
    THREE_MONTHS = "3m"
    SIX_MONTHS = "6m"
    ONE_YEAR = "1y"
    FIVE_YEARS = "5y"
    MAXIMUM = "max"


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
    sync_status: SyncStatus = SyncStatus.UNKNOWN
    last_update: Optional[datetime] = None
    last_successful_sync: Optional[datetime] = None
    last_candle_timestamp: Optional[datetime] = None
    rows_collected: int = 0
    rows_downloaded: int = 0
    rows_rejected: int = 0
    rows_repaired: int = 0
    latency_ms: Optional[float] = None
    sync_latency_ms: Optional[float] = None
    message: str = ""


@dataclass
class DataGap:
    symbol: str
    timeframe: Timeframe
    gap_type: GapType
    expected_timestamp: Optional[datetime] = None
    gap_start: Optional[datetime] = None
    gap_end: Optional[datetime] = None
    status: GapStatus = GapStatus.OPEN
    provider: str = ""
    id: Optional[int] = None
    created_at: Optional[datetime] = None
    repaired_at: Optional[datetime] = None


@dataclass
class GapReport:
    gaps: list[DataGap]
    duplicates: int = 0
    out_of_order: int = 0
    overlaps: int = 0
    missing: int = 0


@dataclass
class RepairResult:
    attempted: int = 0
    repaired: int = 0
    unresolved: int = 0
    rows_inserted: int = 0


@dataclass
class ImportResult:
    symbol: str
    timeframe: Timeframe
    range_label: str
    rows_imported: int = 0
    rows_skipped: int = 0
    rows_rejected: int = 0
    gaps_repaired: int = 0
    duration_ms: float = 0.0
    status: str = "completed"
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

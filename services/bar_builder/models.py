"""Bar builder models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from shared.types.models import Candle, Timeframe


@dataclass(frozen=True)
class BarGap:
    """Metadata for a missing bar in a series."""

    expected_timestamp: datetime
    timeframe: Timeframe
    symbol: str


@dataclass
class BuiltBar:
    """Deterministic bar with optional gap tracking."""

    candle: Candle
    is_complete: bool = True
    gap_before: BarGap | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

"""UTC session windows for Liquidity Engine v1.

Session definitions are fixed in UTC (deterministic; not machine-local).
A session high/low becomes available only after the session window completes
(or at as_of if the window is still open and the extreme has already printed —
but completed-session pools use available_at = session_end).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum

from shared.types.models import Candle


class SessionType(str, Enum):
    ASIA = "asia"
    LONDON = "london"
    NEW_YORK = "new_york"


# Inclusive start hour, exclusive end hour in UTC.
SESSION_UTC_HOURS: dict[SessionType, tuple[int, int]] = {
    SessionType.ASIA: (0, 8),
    SessionType.LONDON: (8, 16),
    SessionType.NEW_YORK: (13, 21),
}


def _utc(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


@dataclass(frozen=True)
class SessionWindow:
    session_type: SessionType
    start: datetime
    end: datetime
    high: float
    low: float
    high_index: int
    low_index: int
    completed: bool

    @property
    def available_at(self) -> datetime:
        """Session extremes are published at session end when completed."""
        return self.end if self.completed else self.end


def session_type_for_hour(hour: int) -> SessionType | None:
    for session, (start, end) in SESSION_UTC_HOURS.items():
        if start <= hour < end:
            return session
    return None


def _session_day_bounds(day: datetime, session: SessionType) -> tuple[datetime, datetime]:
    start_h, end_h = SESSION_UTC_HOURS[session]
    start = day.replace(hour=start_h, minute=0, second=0, microsecond=0)
    end = day.replace(hour=end_h, minute=0, second=0, microsecond=0)
    if end <= start:
        end = end + timedelta(days=1)
    return start, end


def build_session_windows(
    candles: list[Candle],
    *,
    as_of_index: int | None = None,
) -> list[SessionWindow]:
    """Build completed (and optionally in-progress) session OHLC windows."""

    if not candles:
        return []
    end_idx = len(candles) - 1 if as_of_index is None else min(as_of_index, len(candles) - 1)
    if end_idx < 0:
        return []

    as_of_ts = _utc(candles[end_idx].timestamp)
    windows: list[SessionWindow] = []

    # Walk back ~5 calendar days of session slots.
    day0 = as_of_ts.replace(hour=0, minute=0, second=0, microsecond=0)
    for day_offset in range(0, 6):
        day = day0 - timedelta(days=day_offset)
        for session in (SessionType.ASIA, SessionType.LONDON, SessionType.NEW_YORK):
            start, end = _session_day_bounds(day, session)
            if start > as_of_ts:
                continue
            completed = end <= as_of_ts
            highs: list[tuple[int, float]] = []
            lows: list[tuple[int, float]] = []
            for i in range(0, end_idx + 1):
                ts = _utc(candles[i].timestamp)
                if start <= ts < end:
                    highs.append((i, candles[i].high))
                    lows.append((i, candles[i].low))
            if not highs:
                continue
            hi_i, hi = max(highs, key=lambda x: x[1])
            lo_i, lo = min(lows, key=lambda x: x[1])
            # Only emit completed sessions for pool publication (no future session).
            if not completed:
                continue
            windows.append(
                SessionWindow(
                    session_type=session,
                    start=start,
                    end=end,
                    high=hi,
                    low=lo,
                    high_index=hi_i,
                    low_index=lo_i,
                    completed=True,
                )
            )
    windows.sort(key=lambda w: w.end)
    return windows

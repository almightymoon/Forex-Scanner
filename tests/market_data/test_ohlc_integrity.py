"""OHLC integrity: malformed bars, gaps, duplicates, UTC — no manufactured fills."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from shared.market_data import validate_candle_series, validate_ohlc_values
from shared.types.models import Candle, Timeframe


def _c(
    ts: datetime,
    o: float,
    h: float,
    l: float,
    c: float,
    *,
    tf: Timeframe = Timeframe.H1,
) -> Candle:
    return Candle(
        symbol="EURUSD",
        timeframe=tf,
        timestamp=ts,
        open=o,
        high=h,
        low=l,
        close=c,
        volume=10,
    )


def test_rejects_invalid_ohlc():
    ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
    assert validate_ohlc_values(_c(ts, 1.1, 1.0, 1.05, 1.08)) == "high_lt_low"
    assert validate_ohlc_values(_c(ts, 1.1, 1.2, 1.0, 1.05)) is None
    assert validate_ohlc_values(_c(ts, 0, 1.2, 1.0, 1.05)) == "non_positive_price"


def test_duplicate_and_gap_without_fill():
    start = datetime(2024, 6, 1, 0, 0, tzinfo=timezone.utc)
    bars = [
        _c(start, 1.1, 1.12, 1.09, 1.11),
        _c(start, 1.1, 1.12, 1.09, 1.11),  # duplicate
        _c(start + timedelta(hours=1), 1.11, 1.13, 1.10, 1.12),
        _c(start + timedelta(hours=3), 1.12, 1.14, 1.11, 1.13),  # gap of 1 hour
    ]
    report = validate_candle_series(bars)
    assert len(report.duplicate_timestamps) == 1
    assert len(report.gaps) == 1
    assert len(report.valid) == 3
    # Never invent a bar for the missing hour
    assert all(c.timestamp != start + timedelta(hours=2) for c in report.valid)


def test_naive_timestamps_normalized_to_utc():
    start = datetime(2024, 6, 1, 12, 0, 0)  # naive
    report = validate_candle_series([_c(start, 1.1, 1.12, 1.09, 1.11)])
    assert report.valid[0].timestamp.tzinfo is not None
    assert report.valid[0].timestamp.utcoffset() == timedelta(0)

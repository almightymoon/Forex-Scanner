"""Shared OHLC integrity checks for Candle series.

Used by market-data paths to validate bars without manufacturing fills.
Gaps are reported explicitly; missing bars are never invented.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from shared.types.models import Candle, Timeframe

# Keep in sync with services.bar_builder.constants.TF_SECONDS (shared must not import services).
_TF_SECONDS: dict[Timeframe, int] = {
    Timeframe.M1: 60,
    Timeframe.M5: 300,
    Timeframe.M15: 900,
    Timeframe.M30: 1800,
    Timeframe.H1: 3600,
    Timeframe.H4: 14400,
    Timeframe.D1: 86400,
    Timeframe.W1: 604800,
}


@dataclass(frozen=True)
class OHLCIssue:
    index: int
    timestamp: datetime | None
    code: str
    message: str


@dataclass
class OHLCIntegrityReport:
    valid: list[Candle] = field(default_factory=list)
    rejected: list[tuple[Candle | None, OHLCIssue]] = field(default_factory=list)
    gaps: list[dict[str, Any]] = field(default_factory=list)
    duplicate_timestamps: list[datetime] = field(default_factory=list)
    out_of_order: bool = False

    @property
    def ok(self) -> bool:
        return not self.rejected and not self.out_of_order

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid_count": len(self.valid),
            "rejected_count": len(self.rejected),
            "gap_count": len(self.gaps),
            "duplicate_count": len(self.duplicate_timestamps),
            "out_of_order": self.out_of_order,
            "gaps": list(self.gaps),
            "duplicates": [ts.isoformat() for ts in self.duplicate_timestamps],
            "rejected": [
                {
                    "index": issue.index,
                    "timestamp": issue.timestamp.isoformat() if issue.timestamp else None,
                    "code": issue.code,
                    "message": issue.message,
                }
                for _, issue in self.rejected
            ],
        }


def _utc(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


def validate_ohlc_values(candle: Candle) -> str | None:
    """Return a rejection reason or None if OHLC relationships are valid."""
    if candle.open <= 0 or candle.high <= 0 or candle.low <= 0 or candle.close <= 0:
        return "non_positive_price"
    if candle.high < candle.low:
        return "high_lt_low"
    if candle.high < candle.open or candle.high < candle.close:
        return "high_lt_open_or_close"
    if candle.low > candle.open or candle.low > candle.close:
        return "low_gt_open_or_close"
    if candle.volume is not None and candle.volume < 0:
        return "negative_volume"
    return None


def expected_bar_delta(timeframe: Timeframe) -> timedelta | None:
    seconds = _TF_SECONDS.get(timeframe)
    if seconds is None:
        return None
    return timedelta(seconds=seconds)


def validate_candle_series(
    candles: list[Candle],
    *,
    detect_gaps: bool = True,
    reject_duplicates: bool = True,
    normalize_utc: bool = True,
) -> OHLCIntegrityReport:
    """Validate a candle series. Never invents bars to fill gaps."""

    report = OHLCIntegrityReport()
    if not candles:
        return report

    seen: set[datetime] = set()
    prev_ts: datetime | None = None
    expected_delta = expected_bar_delta(candles[0].timeframe)

    for index, candle in enumerate(candles):
        ts = _utc(candle.timestamp) if normalize_utc else candle.timestamp
        reason = validate_ohlc_values(candle)
        if reason:
            report.rejected.append(
                (
                    candle,
                    OHLCIssue(index, ts, reason, f"Invalid OHLC: {reason}"),
                )
            )
            continue

        if prev_ts is not None and ts < prev_ts:
            report.out_of_order = True
            report.rejected.append(
                (
                    candle,
                    OHLCIssue(index, ts, "out_of_order", "Timestamp precedes previous bar"),
                )
            )
            continue

        if reject_duplicates and ts in seen:
            report.duplicate_timestamps.append(ts)
            report.rejected.append(
                (
                    candle,
                    OHLCIssue(index, ts, "duplicate_timestamp", "Duplicate timestamp"),
                )
            )
            continue

        if (
            detect_gaps
            and prev_ts is not None
            and expected_delta is not None
            and ts > prev_ts + expected_delta
        ):
            # Explicit gap — do not manufacture candles.
            report.gaps.append(
                {
                    "after": prev_ts.isoformat(),
                    "before": ts.isoformat(),
                    "expected_delta_seconds": int(expected_delta.total_seconds()),
                    "actual_delta_seconds": int((ts - prev_ts).total_seconds()),
                }
            )

        seen.add(ts)
        if normalize_utc and candle.timestamp != ts:
            candle = Candle(
                symbol=candle.symbol,
                timeframe=candle.timeframe,
                timestamp=ts,
                open=candle.open,
                high=candle.high,
                low=candle.low,
                close=candle.close,
                volume=candle.volume,
                tick_volume=getattr(candle, "tick_volume", 0) or 0,
                spread=candle.spread,
            )
        report.valid.append(candle)
        prev_ts = ts

    return report

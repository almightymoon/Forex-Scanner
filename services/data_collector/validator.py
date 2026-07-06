"""Validate candles and ticks before database insertion."""

from datetime import datetime, timedelta, timezone
from typing import Optional

from services.data_collector.config import get_collector_config
from services.data_collector.models import CollectedCandle, CollectedTick, ValidationResult
from services.data_collector.normalizer import DataNormalizer
from shared.types.models import Timeframe


class DataValidator:
    """
    Reject invalid market data before it reaches the database.

    Checks: missing fields, duplicates, invalid OHLC, negative prices,
    future timestamps, and gap detection.
    """

    def __init__(self, config=None):
        self.config = config or get_collector_config().validation

    def validate_candle(self, candle: CollectedCandle) -> tuple[bool, Optional[str]]:
        if candle.high < candle.low:
            return False, "high < low"
        if candle.open < candle.low or candle.open > candle.high:
            return False, "open outside high/low range"
        if candle.close < candle.low or candle.close > candle.high:
            return False, "close outside high/low range"
        if candle.high <= 0 or candle.low <= 0 or candle.open <= 0 or candle.close <= 0:
            return False, "non-positive price"
        if candle.volume < 0:
            return False, "negative volume"

        now = datetime.now(timezone.utc)
        skew = timedelta(seconds=self.config.max_future_skew_seconds)
        ts = candle.timestamp if candle.timestamp.tzinfo else candle.timestamp.replace(tzinfo=timezone.utc)
        if ts > now + skew:
            return False, "future timestamp"

        return True, None

    def validate_tick(self, tick: CollectedTick) -> tuple[bool, Optional[str]]:
        if tick.bid <= 0 or tick.ask <= 0:
            return False, "non-positive bid/ask"
        if tick.ask < tick.bid:
            return False, "ask < bid"
        if tick.volume < 0:
            return False, "negative volume"

        now = datetime.now(timezone.utc)
        skew = timedelta(seconds=self.config.max_future_skew_seconds)
        ts = tick.timestamp if tick.timestamp.tzinfo else tick.timestamp.replace(tzinfo=timezone.utc)
        if ts > now + skew:
            return False, "future timestamp"

        return True, None

    def validate_candles(
        self,
        candles: list[CollectedCandle],
        *,
        detect_gaps: Optional[bool] = None,
    ) -> ValidationResult:
        detect_gaps = self.config.gap_detection_enabled if detect_gaps is None else detect_gaps
        valid: list[CollectedCandle] = []
        rejected: list[tuple[CollectedCandle, str]] = []
        warnings: list[str] = []
        seen: set[datetime] = set()

        sorted_candles = sorted(candles, key=lambda c: c.timestamp)

        for candle in sorted_candles:
            ok, reason = self.validate_candle(candle)
            if not ok:
                rejected.append((candle, reason or "invalid"))
                continue

            if self.config.reject_duplicates:
                if candle.timestamp in seen:
                    rejected.append((candle, "duplicate timestamp"))
                    continue
                seen.add(candle.timestamp)

            valid.append(candle)

        gaps: list[tuple[datetime, datetime]] = []
        if detect_gaps and len(valid) >= 2:
            interval = DataNormalizer.expected_interval_seconds(valid[0].timeframe)
            for prev, curr in zip(valid, valid[1:]):
                delta = (curr.timestamp - prev.timestamp).total_seconds()
                if delta > interval * 1.5:
                    gaps.append((prev.timestamp, curr.timestamp))
                    warnings.append(
                        f"gap detected: {prev.timestamp.isoformat()} → {curr.timestamp.isoformat()} "
                        f"({int(delta)}s, expected ~{interval}s)"
                    )

        return ValidationResult(
            valid=valid,
            rejected=rejected,
            warnings=warnings,
            gaps_detected=gaps,
        )

    def filter_ticks(self, ticks: list[CollectedTick]) -> tuple[list[CollectedTick], list[tuple[CollectedTick, str]]]:
        valid: list[CollectedTick] = []
        rejected: list[tuple[CollectedTick, str]] = []
        for tick in ticks:
            ok, reason = self.validate_tick(tick)
            if ok:
                valid.append(tick)
            else:
                rejected.append((tick, reason or "invalid"))
        return valid, rejected

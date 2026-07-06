"""Expanded data validation — reject corrupt candles before database insertion."""

from datetime import datetime, timedelta, timezone
from typing import Optional

from services.data_collector.config import get_collector_config
from services.data_collector.models import CollectedCandle, CollectedTick, ValidationResult
from services.data_collector.normalizer import DataNormalizer
from shared.types.models import Timeframe


class DataValidator:
    """
    Reject invalid market data before it reaches the database.

    Validates OHLC relationships, timestamps, duplicates, price spikes,
    spreads, and volume.
    """

    def __init__(self, config=None):
        self.config = config or get_collector_config().validation
        self._last_close: dict[str, float] = {}

    def validate_candle(
        self,
        candle: CollectedCandle,
        *,
        prev_close: Optional[float] = None,
    ) -> tuple[bool, Optional[str]]:
        # OHLC relationships
        if candle.high < candle.low:
            return False, "high < low"
        if candle.high < candle.open:
            return False, "high < open"
        if candle.high < candle.close:
            return False, "high < close"
        if candle.low > candle.open:
            return False, "low > open"
        if candle.low > candle.close:
            return False, "low > close"
        if candle.open <= 0 or candle.close <= 0:
            return False, "non-positive open/close"
        if candle.high <= 0 or candle.low <= 0:
            return False, "non-positive high/low"

        # Volume
        if candle.volume < 0:
            return False, "negative volume"
        if self.config.require_volume and candle.volume == 0:
            return False, "missing volume"

        # Spread sanity (high-low relative to price)
        spread = candle.high - candle.low
        mid = (candle.high + candle.low) / 2
        if mid > 0 and spread / mid > self.config.max_spread_ratio:
            return False, "invalid spread"

        # Future timestamp
        now = datetime.now(timezone.utc)
        skew = timedelta(seconds=self.config.max_future_skew_seconds)
        ts = self._utc(candle.timestamp)
        if ts > now + skew:
            return False, "future timestamp"

        # Price spike detection
        ref = prev_close or self._last_close.get(candle.symbol)
        if ref and ref > 0:
            change = abs(candle.close - ref) / ref
            if change > self.config.max_price_spike_ratio:
                return False, f"price spike ({change:.1%})"

        return True, None

    def validate_tick(self, tick: CollectedTick) -> tuple[bool, Optional[str]]:
        if tick.bid <= 0 or tick.ask <= 0:
            return False, "non-positive bid/ask"
        if tick.ask < tick.bid:
            return False, "ask < bid"
        if tick.volume < 0:
            return False, "negative volume"

        spread = tick.ask - tick.bid
        if tick.bid > 0 and spread / tick.bid > self.config.max_spread_ratio:
            return False, "invalid tick spread"

        now = datetime.now(timezone.utc)
        skew = timedelta(seconds=self.config.max_future_skew_seconds)
        if self._utc(tick.timestamp) > now + skew:
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

        sorted_candles = sorted(candles, key=lambda c: self._utc(c.timestamp))
        prev_close: Optional[float] = None

        for candle in sorted_candles:
            ok, reason = self.validate_candle(candle, prev_close=prev_close)
            if not ok:
                rejected.append((candle, reason or "invalid"))
                continue

            ts = self._utc(candle.timestamp)
            if self.config.reject_duplicates:
                if ts in seen:
                    rejected.append((candle, "duplicate timestamp"))
                    continue
                seen.add(ts)

            valid.append(candle)
            prev_close = candle.close
            self._last_close[candle.symbol] = candle.close

        gaps: list[tuple[datetime, datetime]] = []
        if detect_gaps and len(valid) >= 2:
            interval = DataNormalizer.expected_interval_seconds(valid[0].timeframe)
            for prev, curr in zip(valid, valid[1:]):
                delta = (self._utc(curr.timestamp) - self._utc(prev.timestamp)).total_seconds()
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

    @staticmethod
    def _utc(ts: datetime) -> datetime:
        if ts.tzinfo is None:
            return ts.replace(tzinfo=timezone.utc)
        return ts.astimezone(timezone.utc)

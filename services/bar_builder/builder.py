"""
Deterministic bar builder — UTC-aligned OHLCV from ticks.

No swing logic. Output is reproducible for identical tick input.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Iterable, Sequence

from shared.types.models import Candle, Tick, Timeframe

from services.bar_builder.constants import TF_SECONDS, SUPPORTED_TIMEFRAMES
from services.bar_builder.models import BarGap, BuiltBar

logger = logging.getLogger("fxnav.bar_builder")


class BarBuilder:
    """Build OHLCV bars from tick streams with deterministic UTC bucketing."""

    def __init__(self, symbol: str, timeframe: Timeframe):
        self.symbol = symbol.upper()
        self.timeframe = timeframe
        self._interval = TF_SECONDS.get(timeframe, 3600)

    @staticmethod
    def bucket_timestamp(ts: datetime, interval_seconds: int) -> datetime:
        """Align timestamp to UTC bar open."""
        ts = ts.astimezone(timezone.utc)
        epoch = int(ts.timestamp())
        bucket_epoch = epoch - (epoch % interval_seconds)
        return datetime.fromtimestamp(bucket_epoch, tz=timezone.utc)

    def from_ticks(
        self,
        ticks: Sequence[tuple[datetime, float, float, float]],
    ) -> list[BuiltBar]:
        """
        Aggregate sorted tick tuples (timestamp, bid, ask, volume).

        Deterministic: identical ticks always produce identical bars.
        """
        if not ticks:
            return []

        buckets: dict[datetime, dict] = {}
        for ts, bid, ask, vol in sorted(ticks, key=lambda x: x[0]):
            mid = (bid + ask) / 2
            bucket_ts = self.bucket_timestamp(ts, self._interval)
            b = buckets.get(bucket_ts)
            if b is None:
                buckets[bucket_ts] = {
                    "timestamp": bucket_ts,
                    "open": mid,
                    "high": mid,
                    "low": mid,
                    "close": mid,
                    "volume": int(vol),
                    "spread_sum": ask - bid,
                    "tick_count": 1,
                }
            else:
                b["high"] = max(b["high"], mid)
                b["low"] = min(b["low"], mid)
                b["close"] = mid
                b["volume"] += int(vol)
                b["spread_sum"] += ask - bid
                b["tick_count"] += 1

        bars: list[BuiltBar] = []
        sorted_ts = sorted(buckets.keys())
        prev_ts: datetime | None = None

        for bucket_ts in sorted_ts:
            b = buckets[bucket_ts]
            gap = None
            if prev_ts is not None:
                expected_next = datetime.fromtimestamp(
                    int(prev_ts.timestamp()) + self._interval, tz=timezone.utc
                )
                if bucket_ts > expected_next:
                    gap = BarGap(
                        expected_timestamp=expected_next,
                        timeframe=self.timeframe,
                        symbol=self.symbol,
                    )

            candle = Candle(
                symbol=self.symbol,
                timeframe=self.timeframe,
                timestamp=bucket_ts,
                open=b["open"],
                high=b["high"],
                low=b["low"],
                close=b["close"],
                volume=b["volume"],
                spread=b["spread_sum"] / b["tick_count"] if b["tick_count"] else None,
            )
            bars.append(BuiltBar(candle=candle, gap_before=gap))
            prev_ts = bucket_ts

        logger.info(
            "bar_builder.built",
            extra={
                "symbol": self.symbol,
                "timeframe": self.timeframe.value,
                "bar_count": len(bars),
                "gaps": sum(1 for b in bars if b.gap_before),
            },
        )
        return bars

    def from_tick_objects(self, ticks: Iterable[Tick]) -> list[BuiltBar]:
        tuples = [(t.timestamp, t.bid, t.ask, float(t.volume or 0)) for t in ticks]
        return self.from_ticks(tuples)

    def to_candles(self, bars: list[BuiltBar]) -> list[Candle]:
        return [b.candle for b in bars]

    @classmethod
    def build_all_timeframes(
        cls,
        symbol: str,
        m1_ticks: Sequence[tuple[datetime, float, float, float]],
    ) -> dict[Timeframe, list[Candle]]:
        """Build M1 from ticks, then rollup higher timeframes internally."""
        m1_builder = cls(symbol, Timeframe.M1)
        m1_bars = m1_builder.from_ticks(m1_ticks)
        m1_candles = m1_builder.to_candles(m1_bars)

        from services.bar_builder.rollup import rollup_bars

        result: dict[Timeframe, list[Candle]] = {Timeframe.M1: m1_candles}
        current = m1_candles
        for tf in SUPPORTED_TIMEFRAMES[1:]:
            current = rollup_bars(current, tf)
            result[tf] = current
        return result

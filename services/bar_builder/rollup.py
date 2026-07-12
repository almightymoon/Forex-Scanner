"""Roll up lower-timeframe bars into higher timeframes — deterministic."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from shared.types.models import Candle, Timeframe

from services.bar_builder.constants import TF_SECONDS
from services.bar_builder.builder import BarBuilder

logger = logging.getLogger("fxnav.bar_builder.rollup")


def rollup_bars(candles: list[Candle], target: Timeframe) -> list[Candle]:
    """
    Aggregate candles into a higher timeframe.

    Input candles must be sorted chronologically. Same input always yields same output.
    """
    if not candles:
        return []

    interval = TF_SECONDS.get(target, 3600)
    symbol = candles[0].symbol
    buckets: dict[datetime, list[Candle]] = {}

    for c in candles:
        bucket_ts = BarBuilder.bucket_timestamp(c.timestamp, interval)
        buckets.setdefault(bucket_ts, []).append(c)

    rolled: list[Candle] = []
    for bucket_ts in sorted(buckets.keys()):
        group = buckets[bucket_ts]
        rolled.append(
            Candle(
                symbol=symbol,
                timeframe=target,
                timestamp=bucket_ts,
                open=group[0].open,
                high=max(x.high for x in group),
                low=min(x.low for x in group),
                close=group[-1].close,
                volume=sum(x.volume for x in group),
                tick_volume=sum(getattr(x, "tick_volume", 0) or 0 for x in group),
            )
        )

    logger.debug(
        "bar_builder.rollup",
        extra={"target": target.value, "input": len(candles), "output": len(rolled)},
    )
    return rolled

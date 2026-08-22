"""Aggregate lower-TF candles into higher timeframes for offline MTF bias."""

from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timezone

from shared.types.models import Candle, Timeframe

from services.bar_builder.constants import TF_SECONDS


def _bucket_start(ts: datetime, seconds: int) -> datetime:
    aware = ts if ts.tzinfo is not None else ts.replace(tzinfo=timezone.utc)
    epoch = int(aware.timestamp())
    floored = epoch - (epoch % seconds)
    out = datetime.fromtimestamp(floored, tz=timezone.utc)
    if ts.tzinfo is None:
        return out.replace(tzinfo=None)
    return out.astimezone(ts.tzinfo)


def aggregate_candles(candles: list[Candle], target: Timeframe) -> list[Candle]:
    """Resample candles into ``target`` OHLC bars (causal, left-closed buckets)."""

    if not candles:
        return []
    if candles[0].timeframe is target:
        return list(candles)

    seconds = TF_SECONDS.get(target)
    if seconds is None:
        raise ValueError(f"Unsupported aggregate target: {target}")

    buckets: OrderedDict[datetime, list[Candle]] = OrderedDict()
    for c in candles:
        key = _bucket_start(c.timestamp, seconds)
        buckets.setdefault(key, []).append(c)

    out: list[Candle] = []
    symbol = candles[0].symbol
    for key, group in buckets.items():
        out.append(
            Candle(
                symbol=symbol,
                timeframe=target,
                timestamp=key,
                open=group[0].open,
                high=max(c.high for c in group),
                low=min(c.low for c in group),
                close=group[-1].close,
                volume=sum(c.volume for c in group),
                tick_volume=sum((c.tick_volume or 0) for c in group) or None,
                spread=group[-1].spread,
            )
        )
    return out

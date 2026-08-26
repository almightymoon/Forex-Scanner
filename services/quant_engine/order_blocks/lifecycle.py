"""Causal Order Block detection and lifecycle (no last-N truncation).

Creation (same displacement rule as legacy SMC):
  Bullish: down candle at i, strong up at i+1 (body_i+1 > 1.5 * body_i)
  Bearish: up candle at i, strong down at i+1
  Zone = [low, high] of candle i; available at confirmation index i+1.

Lifecycle (bars after created_index):
  TOUCHED: any later bar range intersects OB
  MITIGATED: close through opposite side
    Bullish OB: close < price_low
    Bearish OB: close > price_high

No expiration.
"""

from __future__ import annotations

from shared.types.models import Candle, SignalDirection, Timeframe

from services.quant_engine.order_blocks.models import OBStatus, OrderBlockZone, OrderBlockZoneSet

OB_ZONE_ALGORITHM_VERSION = "1.0.0"


def _zone_id(direction: SignalDirection, source: int, lo: float, hi: float) -> str:
    return f"ob-{direction.value}-{source}-{lo:.5f}-{hi:.5f}"


def _update_ob(zone: OrderBlockZone, candles: list[Candle], as_of: int) -> OrderBlockZone:
    if zone.created_index >= as_of:
        return zone

    lo, hi = zone.price_low, zone.price_high
    first_touch = zone.first_touch_index
    first_touch_ts = zone.first_touch_timestamp
    mit_idx = zone.mitigation_index
    mit_ts = zone.mitigation_timestamp
    status = zone.status

    for j in range(zone.created_index + 1, as_of + 1):
        c = candles[j]
        intersects = c.high >= lo and c.low <= hi
        if intersects and first_touch is None:
            first_touch = j
            first_touch_ts = c.timestamp
            if status is OBStatus.ACTIVE:
                status = OBStatus.TOUCHED

        if zone.direction is SignalDirection.BUY:
            if c.close < lo:
                status = OBStatus.MITIGATED
                mit_idx = j
                mit_ts = c.timestamp
                break
        else:
            if c.close > hi:
                status = OBStatus.MITIGATED
                mit_idx = j
                mit_ts = c.timestamp
                break

    return OrderBlockZone(
        zone_id=zone.zone_id,
        symbol=zone.symbol,
        timeframe=zone.timeframe,
        direction=zone.direction,
        price_low=lo,
        price_high=hi,
        source_candle_index=zone.source_candle_index,
        created_index=zone.created_index,
        created_timestamp=zone.created_timestamp,
        impulse_ratio=zone.impulse_ratio,
        status=status,
        first_touch_index=first_touch,
        first_touch_timestamp=first_touch_ts,
        mitigation_index=mit_idx,
        mitigation_timestamp=mit_ts,
        age_bars=max(0, as_of - zone.created_index),
    )


def detect_order_block_zones(
    candles: list[Candle],
    *,
    symbol: str | None = None,
    timeframe: Timeframe | str | None = None,
    as_of_index: int | None = None,
) -> OrderBlockZoneSet:
    if not candles:
        return OrderBlockZoneSet(symbol=symbol or "", timeframe="H1", as_of_index=-1, zones=())

    end = len(candles) - 1 if as_of_index is None else int(as_of_index)
    end = max(-1, min(end, len(candles) - 1))
    sym = symbol or candles[0].symbol
    tf = timeframe
    if isinstance(tf, Timeframe):
        tf_s = tf.value
    elif tf:
        tf_s = str(tf)
    else:
        tf_s = candles[0].timeframe.value

    raw: list[OrderBlockZone] = []
    # Need confirmation candle i+1 <= end
    for i in range(3, end):
        c = candles[i]
        nxt = candles[i + 1]
        body = abs(c.close - c.open)
        next_body = abs(nxt.close - nxt.open)
        if body <= 0:
            continue
        created = i + 1
        if c.close < c.open and nxt.close > nxt.open and next_body > body * 1.5:
            direction = SignalDirection.BUY
            impulse = next_body / body
        elif c.close > c.open and nxt.close < nxt.open and next_body > body * 1.5:
            direction = SignalDirection.SELL
            impulse = next_body / body
        else:
            continue
        lo, hi = float(c.low), float(c.high)
        raw.append(
            OrderBlockZone(
                zone_id=_zone_id(direction, i, lo, hi),
                symbol=sym,
                timeframe=tf_s,
                direction=direction,
                price_low=lo,
                price_high=hi,
                source_candle_index=i,
                created_index=created,
                created_timestamp=nxt.timestamp,
                impulse_ratio=impulse,
                status=OBStatus.ACTIVE,
            )
        )

    zones = tuple(_update_ob(z, candles, end) for z in raw)
    zones = tuple(sorted(zones, key=lambda z: (z.created_index, z.zone_id)))
    return OrderBlockZoneSet(
        symbol=sym,
        timeframe=tf_s,
        as_of_index=end,
        zones=zones,
        algorithm_version=OB_ZONE_ALGORITHM_VERSION,
    )

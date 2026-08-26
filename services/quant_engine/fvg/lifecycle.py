"""Causal FVG detection and lifecycle (no last-N truncation).

Creation (3-candle imbalance, available at index of candle 3):
  Bullish: c1.high < c3.low → zone [c1.high, c3.low]
  Bearish: c1.low > c3.high → zone [c3.high, c1.low]

Lifecycle (bars after created_index only):
  TOUCH / PARTIAL: range intersects zone; fill_ratio from deepest revisit
  MITIGATED (full fill):
    Bullish: any later low <= lower_bound
    Bearish: any later high >= upper_bound

No expiration. Zones persist until mitigated (mitigated zones remain in the set).
"""

from __future__ import annotations

from shared.types.models import Candle, SignalDirection, Timeframe

from services.quant_engine.fvg.models import FVGStatus, FVGZone, FVGZoneSet

FVG_ZONE_ALGORITHM_VERSION = "1.0.0"


def _zone_id(direction: SignalDirection, created: int, lo: float, hi: float) -> str:
    return f"fvg-{direction.value}-{created}-{lo:.5f}-{hi:.5f}"


def _update_fvg(zone: FVGZone, candles: list[Candle], as_of: int) -> FVGZone:
    if zone.created_index >= as_of:
        return FVGZone(
            zone_id=zone.zone_id,
            symbol=zone.symbol,
            timeframe=zone.timeframe,
            direction=zone.direction,
            lower_bound=zone.lower_bound,
            upper_bound=zone.upper_bound,
            created_index=zone.created_index,
            created_timestamp=zone.created_timestamp,
            source_candle_indices=zone.source_candle_indices,
            status=FVGStatus.ACTIVE,
            fill_ratio=0.0,
            age_bars=max(0, as_of - zone.created_index),
        )

    lo, hi = zone.lower_bound, zone.upper_bound
    gap = hi - lo
    if gap <= 0:
        return zone

    first_touch: int | None = None
    first_touch_ts = None
    mit_idx: int | None = None
    mit_ts = None
    fill = 0.0
    status = FVGStatus.ACTIVE

    for j in range(zone.created_index + 1, as_of + 1):
        c = candles[j]
        intersects = c.high >= lo and c.low <= hi

        if intersects and first_touch is None:
            first_touch = j
            first_touch_ts = c.timestamp

        if zone.direction is SignalDirection.BUY:
            # Fill measured from upper bound downward (wick/low penetration).
            if c.low < hi:
                depth = hi - max(c.low, lo)
                fill = max(fill, min(1.0, depth / gap))
            if c.low <= lo:
                fill = 1.0
                mit_idx = j
                mit_ts = c.timestamp
                status = FVGStatus.MITIGATED
                break
        else:
            # Fill measured from lower bound upward.
            if c.high > lo:
                depth = min(c.high, hi) - lo
                fill = max(fill, min(1.0, depth / gap))
            if c.high >= hi:
                fill = 1.0
                mit_idx = j
                mit_ts = c.timestamp
                status = FVGStatus.MITIGATED
                break

        if status is not FVGStatus.MITIGATED:
            if fill > 0 or first_touch is not None:
                status = FVGStatus.PARTIALLY_FILLED
            else:
                status = FVGStatus.ACTIVE

    if status is not FVGStatus.MITIGATED:
        if fill >= 1.0:
            status = FVGStatus.MITIGATED
        elif fill > 0 or first_touch is not None:
            status = FVGStatus.PARTIALLY_FILLED
        else:
            status = FVGStatus.ACTIVE

    return FVGZone(
        zone_id=zone.zone_id,
        symbol=zone.symbol,
        timeframe=zone.timeframe,
        direction=zone.direction,
        lower_bound=lo,
        upper_bound=hi,
        created_index=zone.created_index,
        created_timestamp=zone.created_timestamp,
        source_candle_indices=zone.source_candle_indices,
        status=status,
        first_touch_index=first_touch,
        first_touch_timestamp=first_touch_ts,
        mitigation_index=mit_idx,
        mitigation_timestamp=mit_ts,
        fill_ratio=min(1.0, fill),
        age_bars=max(0, as_of - zone.created_index),
    )


def detect_fvg_zones(
    candles: list[Candle],
    *,
    symbol: str | None = None,
    timeframe: Timeframe | str | None = None,
    as_of_index: int | None = None,
) -> FVGZoneSet:
    """Detect all FVGs on ``candles[:as_of+1]`` and apply causal lifecycle."""
    if not candles:
        return FVGZoneSet(symbol=symbol or "", timeframe="H1", as_of_index=-1, zones=())

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

    raw: list[FVGZone] = []
    for i in range(2, end + 1):
        c1, c2, c3 = candles[i - 2], candles[i - 1], candles[i]
        if c1.high < c3.low:
            lo, hi = float(c1.high), float(c3.low)
            direction = SignalDirection.BUY
        elif c1.low > c3.high:
            lo, hi = float(c3.high), float(c1.low)
            direction = SignalDirection.SELL
        else:
            continue
        zid = _zone_id(direction, i, lo, hi)
        raw.append(
            FVGZone(
                zone_id=zid,
                symbol=sym,
                timeframe=tf_s,
                direction=direction,
                lower_bound=lo,
                upper_bound=hi,
                created_index=i,
                created_timestamp=c3.timestamp,
                source_candle_indices=(i - 2, i - 1, i),
                status=FVGStatus.ACTIVE,
                fill_ratio=0.0,
                age_bars=0,
            )
        )

    zones = tuple(_update_fvg(z, candles, end) for z in raw)
    zones = tuple(sorted(zones, key=lambda z: (z.created_index, z.zone_id)))
    return FVGZoneSet(
        symbol=sym,
        timeframe=tf_s,
        as_of_index=end,
        zones=zones,
        algorithm_version=FVG_ZONE_ALGORITHM_VERSION,
    )

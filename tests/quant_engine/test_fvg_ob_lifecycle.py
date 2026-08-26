"""FVG / Order Block causal zone lifecycle tests."""

from __future__ import annotations

import time

from services.quant_engine.detection.smc import SMCEngine
from services.quant_engine.fvg.lifecycle import detect_fvg_zones
from services.quant_engine.fvg.models import FVGStatus
from services.quant_engine.fvg.patterns import patterns_from_fvg_zones
from services.quant_engine.order_blocks.lifecycle import detect_order_block_zones
from services.quant_engine.order_blocks.models import OBStatus
from services.quant_engine.pipeline import ANALYSIS_PIPELINE_VERSION, analyze_candle_window
from shared.types.models import Candle, SignalDirection, Timeframe
from tests.fixtures.golden.candles import make_candle


def _flat(i: int, mid: float = 100.0, *, half: float = 0.5) -> Candle:
    return make_candle(i, open_=mid, high=mid + half, low=mid - half, close=mid)


# ---------------------------------------------------------------------------
# Golden FVG fixtures
# ---------------------------------------------------------------------------


def bullish_fvg_series() -> list[Candle]:
    """Bullish FVG created at index 2: c0.high=100 < c2.low=102 → [100, 102]."""
    return [
        make_candle(0, open_=99.5, high=100.0, low=99.0, close=99.8),
        make_candle(1, open_=100.5, high=101.5, low=100.2, close=101.0),  # mid impulse
        make_candle(2, open_=102.2, high=103.0, low=102.0, close=102.5),
        # 3: untouched continuation
        make_candle(3, open_=102.6, high=103.5, low=102.4, close=103.0),
        # 4: partial fill (low into gap but not through)
        make_candle(4, open_=102.8, high=103.0, low=100.8, close=101.5),
        # 5: full mitigation (low <= 100)
        make_candle(5, open_=101.2, high=101.5, low=99.5, close=100.2),
        # pad so SMC min-length callers can use if needed
        *[_flat(6 + i, 100.5) for i in range(20)],
    ]


def bearish_fvg_series() -> list[Candle]:
    """Bearish FVG at index 2: c0.low=102 > c2.high=100 → [100, 102]."""
    return [
        make_candle(0, open_=102.5, high=103.0, low=102.0, close=102.2),
        make_candle(1, open_=101.5, high=101.8, low=100.5, close=100.8),
        make_candle(2, open_=99.8, high=100.0, low=99.0, close=99.5),
        make_candle(3, open_=99.4, high=99.8, low=98.5, close=99.0),
        # partial: high into gap
        make_candle(4, open_=99.2, high=101.2, low=99.0, close=100.5),
        # full: high >= 102
        make_candle(5, open_=100.8, high=102.5, low=100.5, close=101.8),
        *[_flat(6 + i, 101.0) for i in range(20)],
    ]


def multi_fvg_series() -> list[Candle]:
    """Two bullish FVGs that both remain active (no fill)."""
    return [
        make_candle(0, open_=99.5, high=100.0, low=99.0, close=99.8),
        make_candle(1, open_=100.5, high=101.5, low=100.2, close=101.0),
        make_candle(2, open_=102.2, high=103.0, low=102.0, close=102.5),  # FVG A @2 [100,102]
        make_candle(3, open_=103.0, high=103.5, low=102.8, close=103.2),
        make_candle(4, open_=103.5, high=104.5, low=103.2, close=104.0),
        make_candle(5, open_=105.2, high=106.0, low=105.0, close=105.5),  # FVG B @5 [103.5,105]
        make_candle(6, open_=105.6, high=106.5, low=105.4, close=106.0),
        *[_flat(7 + i, 106.0) for i in range(20)],
    ]


# ---------------------------------------------------------------------------
# Golden OB fixtures
# ---------------------------------------------------------------------------


def bullish_ob_series() -> list[Candle]:
    """Bullish OB: down candle at 4, strong up at 5 → zone from candle 4."""
    base = [_flat(i, 100.0) for i in range(4)]
    # source down candle
    base.append(make_candle(4, open_=100.5, high=100.8, low=99.0, close=99.2))
    # confirmation impulse up (body > 1.5 * prior body)
    # prior body = 1.3; need next_body > 1.95
    base.append(make_candle(5, open_=99.5, high=102.5, low=99.4, close=102.2))
    # untouched
    base.append(make_candle(6, open_=102.0, high=103.0, low=101.5, close=102.5))
    # touch (intersects OB [99, 100.8])
    base.append(make_candle(7, open_=101.0, high=101.2, low=100.0, close=100.5))
    # mitigate: close < 99.0
    base.append(make_candle(8, open_=100.0, high=100.2, low=98.0, close=98.5))
    base.extend(_flat(9 + i, 99.0) for i in range(20))
    return base


def bearish_ob_series() -> list[Candle]:
    base = [_flat(i, 100.0) for i in range(4)]
    base.append(make_candle(4, open_=99.5, high=101.0, low=99.2, close=100.8))  # up
    base.append(make_candle(5, open_=100.5, high=100.6, low=97.5, close=97.8))  # strong down
    base.append(make_candle(6, open_=97.9, high=98.5, low=97.0, close=97.5))
    base.append(make_candle(7, open_=98.0, high=100.5, low=97.8, close=100.0))  # touch
    base.append(make_candle(8, open_=100.2, high=102.0, low=100.0, close=101.5))  # close > 101
    base.extend(_flat(9 + i, 101.0) for i in range(20))
    return base


# ---------------------------------------------------------------------------
# FVG lifecycle
# ---------------------------------------------------------------------------


def test_bullish_fvg_creation_and_lifecycle():
    candles = bullish_fvg_series()
    at_create = detect_fvg_zones(candles, as_of_index=2)
    assert len(at_create.zones) == 1
    z = at_create.zones[0]
    assert z.direction is SignalDirection.BUY
    assert z.lower_bound == 100.0
    assert z.upper_bound == 102.0
    assert z.created_index == 2
    assert z.status is FVGStatus.ACTIVE
    assert z.fill_ratio == 0.0

    untouched = detect_fvg_zones(candles, as_of_index=3)
    assert untouched.zones[0].status is FVGStatus.ACTIVE

    partial = detect_fvg_zones(candles, as_of_index=4)
    z4 = partial.zones[0]
    assert z4.status is FVGStatus.PARTIALLY_FILLED
    assert 0 < z4.fill_ratio < 1.0
    assert z4.first_touch_index == 4
    assert z4.mitigation_index is None

    full = detect_fvg_zones(candles, as_of_index=5)
    z5 = full.zones[0]
    assert z5.status is FVGStatus.MITIGATED
    assert z5.fill_ratio == 1.0
    assert z5.mitigation_index == 5


def test_bearish_fvg_lifecycle():
    candles = bearish_fvg_series()
    z = detect_fvg_zones(candles, as_of_index=2).zones[0]
    assert z.direction is SignalDirection.SELL
    assert (z.lower_bound, z.upper_bound) == (100.0, 102.0)

    partial = detect_fvg_zones(candles, as_of_index=4).zones[0]
    assert partial.status is FVGStatus.PARTIALLY_FILLED
    assert 0 < partial.fill_ratio < 1.0

    mit = detect_fvg_zones(candles, as_of_index=5).zones[0]
    assert mit.status is FVGStatus.MITIGATED
    assert mit.mitigation_index == 5


def test_multiple_simultaneous_fvgs():
    candles = multi_fvg_series()
    zs = detect_fvg_zones(candles, as_of_index=6)
    assert len(zs.zones) >= 2
    assert all(z.status in (FVGStatus.ACTIVE, FVGStatus.PARTIALLY_FILLED) for z in zs.active)
    ids = {z.zone_id for z in zs.zones}
    assert len(ids) == len(zs.zones)


def test_fvg_causal_prefix_stable_when_future_appended():
    candles = bullish_fvg_series()
    t = 3
    early = detect_fvg_zones(candles[: t + 1])
    late = detect_fvg_zones(candles, as_of_index=t)
    assert early.to_dict() == late.to_dict()
    # Future mitigation must not leak
    assert early.zones[0].status is FVGStatus.ACTIVE
    future = detect_fvg_zones(candles, as_of_index=5)
    assert future.zones[0].status is FVGStatus.MITIGATED


def test_fvg_no_lookahead_mitigation():
    candles = bullish_fvg_series()
    at_t = detect_fvg_zones(candles, as_of_index=3)
    assert at_t.zones[0].status is FVGStatus.ACTIVE
    assert at_t.zones[0].mitigation_index is None
    at_t10 = detect_fvg_zones(candles, as_of_index=5)
    assert at_t10.zones[0].status is FVGStatus.MITIGATED


# ---------------------------------------------------------------------------
# OB lifecycle
# ---------------------------------------------------------------------------


def test_bullish_ob_creation_and_lifecycle():
    candles = bullish_ob_series()
    at_create = detect_order_block_zones(candles, as_of_index=5)
    assert len(at_create.zones) >= 1
    z = next(z for z in at_create.zones if z.source_candle_index == 4)
    assert z.direction is SignalDirection.BUY
    assert z.price_low == 99.0
    assert z.price_high == 100.8
    assert z.created_index == 5
    assert z.status is OBStatus.ACTIVE

    untouched = detect_order_block_zones(candles, as_of_index=6)
    z6 = next(z for z in untouched.zones if z.source_candle_index == 4)
    assert z6.status is OBStatus.ACTIVE

    touched = detect_order_block_zones(candles, as_of_index=7)
    z7 = next(z for z in touched.zones if z.source_candle_index == 4)
    assert z7.status is OBStatus.TOUCHED
    assert z7.first_touch_index == 7

    mit = detect_order_block_zones(candles, as_of_index=8)
    z8 = next(z for z in mit.zones if z.source_candle_index == 4)
    assert z8.status is OBStatus.MITIGATED
    assert z8.mitigation_index == 8


def test_bearish_ob_lifecycle():
    candles = bearish_ob_series()
    z = next(
        z
        for z in detect_order_block_zones(candles, as_of_index=5).zones
        if z.source_candle_index == 4
    )
    assert z.direction is SignalDirection.SELL
    mit = next(
        z
        for z in detect_order_block_zones(candles, as_of_index=8).zones
        if z.source_candle_index == 4
    )
    assert mit.status is OBStatus.MITIGATED


def test_ob_no_lookahead():
    candles = bullish_ob_series()
    early = detect_order_block_zones(candles, as_of_index=6)
    z = next(z for z in early.zones if z.source_candle_index == 4)
    assert z.status is OBStatus.ACTIVE
    late = detect_order_block_zones(candles, as_of_index=8)
    z2 = next(z for z in late.zones if z.source_candle_index == 4)
    assert z2.status is OBStatus.MITIGATED


def test_ob_causal_prefix():
    candles = bullish_ob_series()
    t = 6
    a = detect_order_block_zones(candles[: t + 1]).to_dict()
    b = detect_order_block_zones(candles, as_of_index=t).to_dict()
    assert a == b


# ---------------------------------------------------------------------------
# Ranking / SMC / pipeline
# ---------------------------------------------------------------------------


def test_ranking_does_not_delete_zones():
    candles = multi_fvg_series()
    zs = detect_fvg_zones(candles, as_of_index=6)
    assert len(zs.zones) >= 2
    pats = patterns_from_fvg_zones(zs, price=106.0, limit=1)
    assert len(pats) == 1
    assert len(zs.zones) >= 2  # full set intact


def test_smc_consumes_zone_sets_not_last_n():
    candles = multi_fvg_series()
    bundle = analyze_candle_window("XAUUSD", Timeframe.H1, candles, evaluate=False)
    assert bundle.fvg_zones is not None
    assert len(bundle.fvg_zones.zones) >= 2
    fvg_pats = [p for p in bundle.smc_patterns if p.pattern_type == "fvg"]
    assert len(fvg_pats) <= 8
    assert all(p.metadata.get("source") == "fvg_lifecycle" for p in fvg_pats)


def test_pipeline_version_bumped():
    assert ANALYSIS_PIPELINE_VERSION == "1.4.0"


def test_live_replay_zone_parity():
    candles = multi_fvg_series()
    a = analyze_candle_window("XAUUSD", Timeframe.H1, candles, evaluate=False)
    b = analyze_candle_window("XAUUSD", Timeframe.H1, list(candles), evaluate=False)
    assert a.fvg_zones is not None and b.fvg_zones is not None
    assert a.ob_zones is not None and b.ob_zones is not None
    assert a.fvg_zones.to_dict() == b.fvg_zones.to_dict()
    assert a.ob_zones.to_dict() == b.ob_zones.to_dict()
    assert a.analytical_fingerprint() == b.analytical_fingerprint()


def test_prefix_vs_full_no_lookahead_pipeline():
    candles = bullish_fvg_series()
    early = analyze_candle_window("XAUUSD", Timeframe.H1, candles[:4], evaluate=False)
    late = analyze_candle_window("XAUUSD", Timeframe.H1, candles[:6], evaluate=False)
    assert early.fvg_zones is not None and late.fvg_zones is not None
    e = early.fvg_zones.zones[0]
    assert e.status is FVGStatus.ACTIVE
    assert late.fvg_zones.zones[0].status is FVGStatus.MITIGATED


def test_performance_realistic_window():
    candles: list[Candle] = []
    price = 2000.0
    for i in range(500):
        if i % 25 == 5:
            candles.append(
                make_candle(i, open_=price - 0.5, high=price, low=price - 1, close=price - 0.2)
            )
            continue
        if i % 25 == 6:
            candles.append(
                make_candle(i, open_=price, high=price + 1, low=price - 0.2, close=price + 0.8)
            )
            price += 0.8
            continue
        if i % 25 == 7:
            lo = price + 1.0
            candles.append(
                make_candle(i, open_=lo + 0.2, high=lo + 1.5, low=lo, close=lo + 1.0)
            )
            price = lo + 1.0
            continue
        o = price
        c = price + 0.15
        candles.append(make_candle(i, open_=o, high=c + 0.2, low=o - 0.2, close=c))
        price = c

    t0 = time.perf_counter()
    zs = detect_fvg_zones(candles)
    obs = detect_order_block_zones(candles)
    elapsed = time.perf_counter() - t0
    assert elapsed < 2.0
    assert zs.as_of_index == 499
    assert obs.as_of_index == 499
    assert len(zs.zones) >= 1


def test_no_duplicate_detector_methods():
    assert not hasattr(SMCEngine, "_detect_fvg")
    assert not hasattr(SMCEngine, "_detect_order_blocks")

"""Liquidity Engine v1 acceptance scenarios (A–E) and causality tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from shared.types.models import Candle, Timeframe, TrendDirection
from swing_engine.models import SwingDirection, SwingScope, SwingTier, DetectedSwing

from services.quant_engine.liquidity import (
    LIQUIDITY_ENGINE_VERSION,
    PoolStatus,
    PoolType,
    SweepKind,
    analyze_liquidity,
    equality_tolerance,
)
from services.quant_engine.liquidity.clustering import cluster_prices
from services.quant_engine.market_structure import analyze_structure


def _ts(i: int) -> datetime:
    # Start Monday 00:00 UTC so Asia/London/NY windows are clean.
    return datetime(2024, 3, 4, tzinfo=timezone.utc) + timedelta(hours=i)


def _c(i: int, high: float, low: float, close: float, *, open_: float | None = None) -> Candle:
    o = open_ if open_ is not None else (high + low) / 2
    return Candle(
        symbol="XAUUSD",
        timeframe=Timeframe.H1,
        timestamp=_ts(i),
        open=o,
        high=high,
        low=low,
        close=close,
        volume=100,
    )


def _swing(pivot: int, direction: SwingDirection, price: float, conf: int) -> DetectedSwing:
    return DetectedSwing(
        timestamp=_ts(pivot),
        price=price,
        direction=direction,
        tier=SwingTier.MAJOR,
        scope=SwingScope.EXTERNAL,
        pivot_index=pivot,
        confirmed=True,
        confirmed_timestamp=_ts(conf),
        confirmation_index=conf,
        confirmation_delay=conf - pivot,
        strength=4,
    )


def test_equality_tolerance_is_atr_aware():
    assert equality_tolerance(10.0) == max(1e-5, 0.15 * 10.0)
    assert equality_tolerance(0.0) == 1e-5


def test_cluster_within_and_outside_tolerance():
    inside = cluster_prices([(1, 2650.20), (5, 2650.24), (9, 2650.22)], tolerance=0.1)
    assert len(inside) == 1
    assert inside[0].touches == 3
    outside = cluster_prices([(1, 2650.0), (5, 2651.5)], tolerance=0.1)
    assert outside == []


def test_scenario_a_equal_high_sweep():
    """Two equal highs then wick through + close back → EQUAL_HIGH + SWEEP_HIGH."""
    candles = [_c(i, 2649.5, 2648.5, 2649.0) for i in range(30)]
    candles[8] = _c(8, 2650.20, 2648.8, 2649.5)
    candles[14] = _c(14, 2650.22, 2648.9, 2649.6)
    candles[20] = _c(20, 2650.55, 2649.0, 2649.70)  # sweep + reject
    swings = [
        _swing(8, SwingDirection.HIGH, 2650.20, 10),
        _swing(14, SwingDirection.HIGH, 2650.22, 16),
        _swing(12, SwingDirection.LOW, 2648.90, 13),
    ]
    snap = analyze_structure(candles, swings)
    liq = analyze_liquidity(candles, snapshot=snap, atr=1.0)
    equals = [p for p in liq.pools if p.pool_type is PoolType.EQUAL_HIGH]
    assert equals
    sweeps = [s for s in liq.sweeps if s.kind is SweepKind.SWEEP_HIGH]
    assert sweeps
    assert liq.algorithm_version == LIQUIDITY_ENGINE_VERSION


def test_scenario_b_equal_low_sweep():
    candles = [_c(i, 2651.0, 2650.0, 2650.5) for i in range(30)]
    candles[8] = _c(8, 2650.8, 2649.80, 2650.2)
    candles[14] = _c(14, 2650.7, 2649.82, 2650.1)
    candles[20] = _c(20, 2650.5, 2649.40, 2650.05)  # pierce low + close back
    swings = [
        _swing(8, SwingDirection.LOW, 2649.80, 10),
        _swing(14, SwingDirection.LOW, 2649.82, 16),
        _swing(11, SwingDirection.HIGH, 2650.70, 12),
    ]
    snap = analyze_structure(candles, swings)
    liq = analyze_liquidity(candles, snapshot=snap, atr=1.0)
    assert any(p.pool_type is PoolType.EQUAL_LOW for p in liq.pools)
    assert any(s.kind is SweepKind.SWEEP_LOW for s in liq.sweeps)


def test_scenario_c_session_high():
    # Asia 00-08 UTC on 2024-03-04
    candles = []
    for i in range(24):
        h = 2650.0 + (0.5 if i == 3 else 0.0)  # asia high at 03:00
        candles.append(_c(i, h + 0.1, h - 0.1, h))
    liq = analyze_liquidity(candles, atr=1.0, as_of_index=20)
    asia_highs = [
        p
        for p in liq.pools
        if p.pool_type is PoolType.SESSION_HIGH
        and p.metadata.get("session_type") == "asia"
    ]
    assert asia_highs
    assert asia_highs[0].price >= 2650.5
    assert asia_highs[0].available_at is not None


def test_scenario_d_breakout_not_sweep():
    candles = [_c(i, 2649.5, 2648.5, 2649.0) for i in range(25)]
    candles[8] = _c(8, 2650.20, 2648.8, 2649.5)
    candles[14] = _c(14, 2650.22, 2648.9, 2649.6)
    # Decisive close above equal high — breakout
    candles[20] = _c(20, 2651.0, 2650.3, 2650.80, open_=2650.40)
    swings = [
        _swing(8, SwingDirection.HIGH, 2650.20, 10),
        _swing(14, SwingDirection.HIGH, 2650.22, 16),
        _swing(12, SwingDirection.LOW, 2648.90, 13),
    ]
    snap = analyze_structure(candles, swings)
    liq = analyze_liquidity(candles, snapshot=snap, atr=1.0)
    breakouts = [s for s in liq.sweeps if s.kind is SweepKind.BREAKOUT]
    assert breakouts
    # Matching pool should be invalidated, not treated as sweep-only
    assert any(p.status is PoolStatus.INVALIDATED for p in liq.pools)


def test_scenario_e_no_lookahead_future_pool():
    candles = [_c(i, 2649.5, 2648.5, 2649.0) for i in range(40)]
    candles[30] = _c(30, 2655.0, 2649.0, 2650.0)  # future high
    swings_early = [_swing(5, SwingDirection.HIGH, 2649.4, 7)]
    swings_full = swings_early + [_swing(30, SwingDirection.HIGH, 2655.0, 32)]

    early = analyze_liquidity(
        candles,
        snapshot=analyze_structure(candles, swings_early, as_of_index=20),
        as_of_index=20,
        atr=1.0,
    )
    # Future structural high must not appear at as_of=20
    assert all(abs(p.price - 2655.0) > 1.0 for p in early.pools)

    later = analyze_liquidity(
        candles,
        snapshot=analyze_structure(candles, swings_full, as_of_index=35),
        as_of_index=35,
        atr=1.0,
    )
    assert any(abs(p.price - 2655.0) < 0.01 for p in later.pools)


def test_structural_pools_from_structure_snapshot():
    candles = [_c(i, 1.11 + 0.001, 1.10, 1.105) for i in range(45)]
    candles[10] = _c(10, 1.101, 1.099, 1.100)
    candles[18] = _c(18, 1.121, 1.118, 1.120)
    candles[24] = _c(24, 1.124, 1.118, 1.122)  # BOS-ish
    candles[28] = _c(28, 1.107, 1.104, 1.105)  # HL
    candles[34] = _c(34, 1.131, 1.128, 1.130)  # HH
    swings = [
        _swing(10, SwingDirection.LOW, 1.100, 12),
        _swing(18, SwingDirection.HIGH, 1.120, 20),
        _swing(28, SwingDirection.LOW, 1.105, 30),
        _swing(34, SwingDirection.HIGH, 1.130, 36),
    ]
    snap = analyze_structure(candles, swings)
    liq = analyze_liquidity(candles, snapshot=snap, atr=0.01)
    assert any(p.pool_type is PoolType.STRUCTURAL_HIGH for p in liq.pools)
    assert any(p.pool_type is PoolType.STRUCTURAL_LOW for p in liq.pools)
    for p in liq.pools:
        assert p.source_timeframe == "H1"


def test_mtf_source_timeframe_preserved():
    candles = [
        Candle(
            symbol="EURUSD",
            timeframe=Timeframe.H4,
            timestamp=_ts(i * 4),
            open=1.1,
            high=1.11,
            low=1.09,
            close=1.105,
            volume=10,
        )
        for i in range(20)
    ]
    liq = analyze_liquidity(candles, timeframe=Timeframe.H4, atr=0.01)
    for p in liq.pools:
        assert p.source_timeframe == "H4"


def test_snapshot_contract_fields():
    candles = [_c(i, 2650.1, 2649.0, 2649.5) for i in range(30)]
    liq = analyze_liquidity(candles, atr=1.0)
    d = liq.to_dict()
    assert "active_pools" in d
    assert "swept_pools" in d
    assert "recent_sweeps" in d
    assert d["algorithm_version"] == LIQUIDITY_ENGINE_VERSION

"""Canonical pipeline: integrity → bar builder → swing engine (deterministic)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from services.bar_builder import BarBuilder, rollup_bars
from shared.market_data import validate_candle_series
from shared.types.models import Timeframe
from swing_engine import SwingEngine, get_config
from swing_engine.versions import DEFAULT_VERSION
from tests.swing_detection.fixtures import swing_candles


def test_rollup_ohlc_invariants_m1_to_h1():
    start = datetime(2024, 1, 2, 0, 0, tzinfo=timezone.utc)
    ticks = [
        (start + timedelta(minutes=i), 1.10 + i * 0.0001, 1.1002 + i * 0.0001, 1.0)
        for i in range(120)
    ]
    m1 = BarBuilder("EURUSD", Timeframe.M1).to_candles(
        BarBuilder("EURUSD", Timeframe.M1).from_ticks(ticks)
    )
    h1 = rollup_bars(m1, Timeframe.H1)
    assert h1
    first_group = [c for c in m1 if c.timestamp >= h1[0].timestamp][:60]
    # First H1 open equals first M1 open in bucket
    bucket = [c for c in m1 if BarBuilder.bucket_timestamp(c.timestamp, 3600) == h1[0].timestamp]
    assert bucket
    assert h1[0].open == bucket[0].open
    assert h1[0].high == max(c.high for c in bucket)
    assert h1[0].low == min(c.low for c in bucket)
    assert h1[0].close == bucket[-1].close


def test_w1_monday_utc_alignment():
    # Wednesday → buckets to Monday
    wed = datetime(2024, 1, 3, 15, 0, tzinfo=timezone.utc)  # Wed
    monday = BarBuilder.bucket_timestamp(wed, 604800, timeframe=Timeframe.W1)
    assert monday.weekday() == 0
    assert monday.hour == 0
    assert monday.date().isoformat() == "2024-01-01"


def test_build_all_includes_w1():
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    ticks = [
        (start + timedelta(hours=i), 1.1, 1.1002, 1.0) for i in range(24 * 14)
    ]
    result = BarBuilder.build_all_timeframes("EURUSD", ticks)
    assert Timeframe.W1 in result
    assert result[Timeframe.W1]


def test_pipeline_deterministic_twice():
    bars = swing_candles(160)
    integrity = validate_candle_series(bars)
    assert integrity.valid
    cfg = get_config(Timeframe.H1, version=DEFAULT_VERSION)
    a = SwingEngine(cfg, version=DEFAULT_VERSION).detect(bars, symbol="EURUSD", timeframe=Timeframe.H1)
    b = SwingEngine(cfg, version=DEFAULT_VERSION).detect(bars, symbol="EURUSD", timeframe=Timeframe.H1)
    assert a.version == DEFAULT_VERSION
    assert [(s.pivot_index, s.price, s.direction, s.confirmed) for s in a.swings] == [
        (s.pivot_index, s.price, s.direction, s.confirmed) for s in b.swings
    ]


def test_no_lookahead_prefix_stability():
    """Confirmed swings on a prefix must not require future bars beyond confirmation."""
    bars = swing_candles(200)
    engine = SwingEngine(get_config(Timeframe.H1, version=DEFAULT_VERSION), version=DEFAULT_VERSION)
    full = engine.detect(bars, symbol="EURUSD", timeframe=Timeframe.H1)
    for swing in full.confirmed_swings:
        conf_idx = swing.confirmation_index
        if conf_idx is None:
            continue
        # Engine must be able to confirm using only bars through confirmation index.
        prefix = bars[: conf_idx + 1]
        partial = engine.detect(prefix, symbol="EURUSD", timeframe=Timeframe.H1)
        matched = [
            s
            for s in partial.confirmed_swings
            if s.pivot_index == swing.pivot_index and s.direction == swing.direction
        ]
        assert matched, (
            f"Swing at pivot {swing.pivot_index} confirmed at {conf_idx} "
            "missing when run on causal prefix"
        )

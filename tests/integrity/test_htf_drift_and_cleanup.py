"""Dead SMC liquidity removal, liquidity SoT, and HTF drift observability."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from shared.types.models import Candle, NewsContext, Timeframe

from services.quant_engine.liquidity.models import (
    LIQUIDITY_ENGINE_VERSION,
    LiquidityPool,
    LiquiditySide,
    LiquiditySnapshot,
    LiquiditySweepEvent,
    PoolStatus,
    PoolStrength,
    PoolType,
    SweepGrade,
    SweepKind,
    SweepQuality,
)
from services.quant_engine.liquidity.patterns import patterns_from_liquidity_snapshot
from services.quant_engine.pipeline import (
    ANALYSIS_PIPELINE_VERSION,
    analyze_candle_window,
    compare_htf_context,
    htf_drift_telemetry_enabled,
    maybe_log_htf_drift,
)
from services.quant_engine.pipeline.htf_drift import HtfDriftKind, compare_htf_series
from services.quant_engine.pipeline.mtf_context import build_htf_bars_from_ltf
from services.scanner_service.data_loader import ScanContext
from services.scanner_service.signal_builder import SignalBuilder
from services.smc_service.smc import SMCEngine
from tests.swing_detection.fixtures import gold_candles


def _ts(i: int) -> datetime:
    return datetime(2024, 6, 3, tzinfo=timezone.utc) + timedelta(hours=i)


def _bar(tf: Timeframe, i: int, o: float, h: float, l: float, c: float) -> Candle:
    return Candle(
        symbol="XAUUSD",
        timeframe=tf,
        timestamp=_ts(i),
        open=o,
        high=h,
        low=l,
        close=c,
        volume=1,
    )


def test_pipeline_version_unchanged_by_cleanup():
    assert ANALYSIS_PIPELINE_VERSION == "1.4.0"


def test_smc_has_no_independent_liquidity_detectors():
    smc = SMCEngine()
    assert not hasattr(smc, "_detect_liquidity_sweeps")
    assert not hasattr(smc, "_detect_equal_levels")
    assert not hasattr(smc, "_legacy_equal_levels")


def test_liquidity_sot_snapshot_drives_smc_patterns():
    """Mutating LiquiditySnapshot changes SMC liquidity patterns; no parallel detect."""
    candles = gold_candles(80, trend=0.3, wave=4.0)
    from services.quant_engine.market_structure import analyze_structure
    from services.quant_engine.swings.boundary import SCAN_SWING_VERSION, obtain_confirmed_swings

    swings = obtain_confirmed_swings(candles, version=SCAN_SWING_VERSION)
    snap = analyze_structure(candles, swings)

    empty = LiquiditySnapshot(
        symbol="XAUUSD",
        timeframe="H1",
        as_of_index=len(candles) - 1,
        pools=(),
        sweeps=(),
        session_tags=(),
        atr=5.0,
        equality_tolerance=0.1,
        algorithm_version=LIQUIDITY_ENGINE_VERSION,
    )
    with_sweep = LiquiditySnapshot(
        symbol="XAUUSD",
        timeframe="H1",
        as_of_index=len(candles) - 1,
        pools=(
            LiquidityPool(
                pool_id="eqh-1",
                pool_type=PoolType.EQUAL_HIGH,
                side=LiquiditySide.SELL_SIDE,
                price=2650.0,
                symbol="XAUUSD",
                source_timeframe="H1",
                scope="EXTERNAL",
                status=PoolStatus.ACTIVE,
                strength=PoolStrength.STRONG,
                strength_score=0.9,
                touches=2,
                created_index=10,
                available_index=12,
                created_at=_ts(10),
                available_at=_ts(12),
                source_reference="test",
            ),
        ),
        sweeps=(
            LiquiditySweepEvent(
                sweep_id="unique-sweep-xyz",
                kind=SweepKind.SWEEP_HIGH,
                pool_id="eqh-1",
                pool_type=PoolType.EQUAL_HIGH,
                level_price=2650.0,
                bar_index=40,
                timestamp=_ts(40),
                penetration=0.5,
                penetration_atr=0.2,
                rejection_pct=80.0,
                grade=SweepGrade.STRONG,
                bias_quality=SweepQuality.CONTINUATION,
            ),
        ),
        session_tags=(),
        atr=5.0,
        equality_tolerance=0.1,
    )

    a = SMCEngine().detect_all(
        candles, "XAUUSD", Timeframe.H1,
        confirmed_swings=swings, structure_snapshot=snap, liquidity_snapshot=empty,
    )
    b = SMCEngine().detect_all(
        candles, "XAUUSD", Timeframe.H1,
        confirmed_swings=swings, structure_snapshot=snap, liquidity_snapshot=with_sweep,
    )
    a_liq = [p for p in a if p.pattern_type in {"equal_highs", "equal_lows", "liquidity_sweep"}]
    b_liq = [p for p in b if p.pattern_type in {"equal_highs", "equal_lows", "liquidity_sweep"}]
    assert a_liq == []
    assert any(p.metadata.get("sweep_id") == "unique-sweep-xyz" for p in b_liq)
    assert any(p.pattern_type == "equal_highs" for p in b_liq)
    assert all(p.metadata.get("source") == "liquidity_engine" for p in b_liq)
    # Adapter agreement
    assert {p.pattern_type for p in patterns_from_liquidity_snapshot(with_sweep)} == {
        p.pattern_type for p in b_liq
    }


def test_patterns_adapter_called_when_snapshot_provided():
    candles = gold_candles(60, trend=0.2, wave=3.0)
    from services.quant_engine.market_structure import analyze_structure
    from services.quant_engine.swings.boundary import SCAN_SWING_VERSION, obtain_confirmed_swings

    swings = obtain_confirmed_swings(candles, version=SCAN_SWING_VERSION)
    snap = analyze_structure(candles, swings)
    empty = LiquiditySnapshot(
        symbol="XAUUSD",
        timeframe="H1",
        as_of_index=len(candles) - 1,
        pools=(),
        sweeps=(),
        session_tags=(),
        atr=1.0,
        equality_tolerance=0.1,
    )
    with patch(
        "services.quant_engine.liquidity.patterns.patterns_from_liquidity_snapshot"
    ) as mocked:
        mocked.return_value = []
        SMCEngine().detect_all(
            candles,
            "XAUUSD",
            Timeframe.H1,
            confirmed_swings=swings,
            structure_snapshot=snap,
            liquidity_snapshot=empty,
        )
        assert mocked.called


def test_htf_drift_exact_match():
    ltf = gold_candles(120, trend=0.3, wave=4.0)
    rollup = build_htf_bars_from_ltf(ltf, targets=(Timeframe.H4,), as_of=ltf[-1].timestamp)
    report = compare_htf_context(
        symbol="XAUUSD",
        ltf_candles=ltf,
        provider_htf=rollup,
        as_of=ltf[-1].timestamp,
        targets=(Timeframe.H4,),
    )
    kinds = {d.kind for d in report.diffs if d.timeframe == "H4"}
    assert HtfDriftKind.MATCH in kinds
    assert HtfDriftKind.OHLC_MISMATCH not in kinds
    assert HtfDriftKind.MISSING_PROVIDER_DATA not in kinds


def test_htf_drift_missing_provider_bar():
    ltf = [_bar(Timeframe.H1, i, 100 + i, 101 + i, 99 + i, 100.5 + i) for i in range(48)]
    rollup = build_htf_bars_from_ltf(ltf, targets=(Timeframe.H4,), as_of=ltf[-1].timestamp)
    provider = {"H4": list(rollup.get("H4", []))[:-1]}  # drop last
    report = compare_htf_context(
        symbol="XAUUSD", ltf_candles=ltf, provider_htf=provider, targets=(Timeframe.H4,)
    )
    assert any(d.kind is HtfDriftKind.MISSING_PROVIDER_DATA for d in report.diffs)


def test_htf_drift_missing_rollup_bar():
    ltf = [_bar(Timeframe.H1, i, 100 + i, 101 + i, 99 + i, 100.5 + i) for i in range(48)]
    rollup = build_htf_bars_from_ltf(ltf, targets=(Timeframe.H4,), as_of=ltf[-1].timestamp)
    h4 = list(rollup.get("H4", []))
    assert h4
    # Provider has an extra synthetic bar rollup lacks
    extra = _bar(Timeframe.H4, 1000, 1, 2, 0.5, 1.5)
    provider = {"H4": h4 + [extra]}
    # Force completed: set as_of far future
    as_of = extra.timestamp + timedelta(hours=5)
    report = compare_htf_context(
        symbol="XAUUSD",
        ltf_candles=ltf,
        provider_htf=provider,
        as_of=as_of,
        targets=(Timeframe.H4,),
    )
    assert any(d.kind is HtfDriftKind.MISSING_ROLLUP_DATA for d in report.diffs)


def test_htf_drift_timestamp_mismatch():
    a = _bar(Timeframe.H4, 0, 1, 2, 0.5, 1.5)
    b = _bar(Timeframe.H4, 4, 1, 2, 0.5, 1.5)
    as_of = _ts(20)
    diffs = compare_htf_series("H4", [a], [b], as_of=as_of)
    kinds = {d.kind for d in diffs}
    assert HtfDriftKind.MISSING_PROVIDER_DATA in kinds or HtfDriftKind.MISSING_ROLLUP_DATA in kinds
    assert HtfDriftKind.TIMESTAMP_MISMATCH in kinds


def test_htf_drift_ohlc_mismatch():
    ts = _ts(0)
    p = Candle(symbol="XAUUSD", timeframe=Timeframe.H4, timestamp=ts, open=1, high=3, low=0.5, close=2, volume=1)
    r = Candle(symbol="XAUUSD", timeframe=Timeframe.H4, timestamp=ts, open=1, high=10, low=0.5, close=2, volume=1)
    as_of = ts + timedelta(hours=4)
    diffs = compare_htf_series("H4", [p], [r], as_of=as_of)
    assert any(d.kind is HtfDriftKind.OHLC_MISMATCH for d in diffs)


def test_htf_drift_expected_small_difference():
    ts = _ts(0)
    p = Candle(symbol="XAUUSD", timeframe=Timeframe.H4, timestamp=ts, open=100.0, high=101.0, low=99.0, close=100.5, volume=1)
    # ~0.05% relative close delta → EXPECTED_DIFFERENCE (< 0.1%)
    r = Candle(symbol="XAUUSD", timeframe=Timeframe.H4, timestamp=ts, open=100.0, high=101.0, low=99.0, close=100.55, volume=1)
    as_of = ts + timedelta(hours=4)
    diffs = compare_htf_series("H4", [p], [r], as_of=as_of)
    assert any(d.kind is HtfDriftKind.EXPECTED_DIFFERENCE for d in diffs)


def test_htf_drift_incomplete_provider_bar():
    open_ts = _ts(0)
    bar = Candle(symbol="XAUUSD", timeframe=Timeframe.H4, timestamp=open_ts, open=1, high=2, low=0.5, close=1.5, volume=1)
    mid = open_ts + timedelta(hours=2)
    diffs = compare_htf_series("H4", [bar], [], as_of=mid)
    assert any(d.kind is HtfDriftKind.COMPLETION_MISMATCH for d in diffs)


def test_htf_drift_incomplete_rollup_bar():
    open_ts = _ts(0)
    bar = Candle(symbol="XAUUSD", timeframe=Timeframe.H4, timestamp=open_ts, open=1, high=2, low=0.5, close=1.5, volume=1)
    mid = open_ts + timedelta(hours=2)
    diffs = compare_htf_series("H4", [], [bar], as_of=mid)
    assert any(d.kind is HtfDriftKind.COMPLETION_MISMATCH for d in diffs)


def test_telemetry_disabled_by_default():
    assert htf_drift_telemetry_enabled() is False
    candles = gold_candles(80, trend=0.2, wave=3.0)
    assert maybe_log_htf_drift(symbol="XAUUSD", ltf_candles=candles, provider_htf={}) is None


def test_telemetry_does_not_alter_analytical_fingerprint(monkeypatch):
    candles = gold_candles(100, trend=0.35, wave=5.0)
    news = NewsContext(score=10)
    base = analyze_candle_window("XAUUSD", Timeframe.H1, candles, news=news, htf_bars={})
    monkeypatch.setenv("HTF_DRIFT_TELEMETRY", "true")
    assert htf_drift_telemetry_enabled() is True
    ctx = ScanContext(
        symbol="XAUUSD", timeframe=Timeframe.H1, candles=candles, news=news, htf_bars={}
    )
    signal = SignalBuilder().build(ctx)
    again = analyze_candle_window("XAUUSD", Timeframe.H1, candles, news=news, htf_bars={})
    assert again.analytical_fingerprint() == base.analytical_fingerprint()
    assert signal.score == base.signal.score
    assert signal.direction == base.signal.direction

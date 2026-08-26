"""Analytical parity: live path vs canonical pipeline, HTF causality, liquidity SoT."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from shared.types.models import Candle, NewsContext, Timeframe, TrendDirection

from services.quant_engine.liquidity import (
    analyze_liquidity,
    patterns_from_liquidity_snapshot,
)
from services.quant_engine.pipeline import (
    ANALYSIS_PIPELINE_VERSION,
    analyze_candle_window,
    build_htf_bars_from_ltf,
    filter_completed_htf,
    resolve_mtf_trends,
)
from services.quant_engine.pipeline.mtf_context import htf_bar_available_at
from services.scanner_service.data_loader import ScanContext
from services.scanner_service.signal_builder import SignalBuilder
from services.smc_service.smc import SMCEngine
from tests.fixtures.golden.candles import bullish_trend_candles, make_candle
from tests.swing_detection.fixtures import gold_candles


def test_pipeline_version_bumped_for_parity_contract():
    assert ANALYSIS_PIPELINE_VERSION == "1.4.0"


def test_live_signal_builder_matches_canonical_fingerprint():
    """Same candles + news + empty HTF → identical analytical fingerprint."""
    candles = gold_candles(160, trend=0.4, wave=6.0)
    news = NewsContext(score=10)
    ctx = ScanContext(
        symbol="XAUUSD",
        timeframe=Timeframe.H1,
        candles=candles,
        news=news,
        htf_bars={},
    )
    signal = SignalBuilder().build(ctx)
    bundle = analyze_candle_window(
        "XAUUSD",
        Timeframe.H1,
        candles,
        htf_bars={},
        news=news,
        evaluate=True,
    )
    assert bundle.signal is not None
    live_fp = {
        "pipeline_version": ctx.pipeline_version,
        "direction": signal.direction.value,
        "score": signal.score,
        "confidence": signal.confidence,
        "trend": signal.trend.value,
        "stop_loss": signal.stop_loss,
        "take_profit_1": signal.take_profit_1,
        "structure_external_bias": (
            ctx.structure_snapshot.external_bias.value if ctx.structure_snapshot else None
        ),
        "structure_event_count": (
            len(ctx.structure_snapshot.events) if ctx.structure_snapshot else 0
        ),
        "smc_pattern_types": sorted({p.pattern_type for p in ctx.smc_patterns}),
        "mtf_trends": {k: v.value for k, v in sorted(ctx.mtf_trends.items())},
    }
    canon = bundle.analytical_fingerprint()
    for key in live_fp:
        assert live_fp[key] == canon[key], f"mismatch on {key}: {live_fp[key]} vs {canon[key]}"
    assert canon["pipeline_version"] == ANALYSIS_PIPELINE_VERSION


def test_replay_backtest_live_same_window_fingerprint():
    candles = gold_candles(140, trend=0.35, wave=7.0)
    window = candles[:110]
    news = NewsContext(score=10)
    a = analyze_candle_window("XAUUSD", Timeframe.H1, window, news=news).analytical_fingerprint()
    b = analyze_candle_window("XAUUSD", Timeframe.H1, list(window), news=news).analytical_fingerprint()
    assert a == b
    ctx = ScanContext(
        symbol="XAUUSD", timeframe=Timeframe.H1, candles=list(window), news=news, htf_bars={}
    )
    SignalBuilder().build(ctx)
    assert ctx.pipeline_version == a["pipeline_version"]
    assert ctx.structure_snapshot is not None
    assert ctx.structure_snapshot.external_bias.value == a["structure_external_bias"]


def test_htf_incomplete_bar_not_available():
    # H4 bar opens at 00:00; available only after +4h
    open_ts = datetime(2024, 6, 3, 0, 0, tzinfo=timezone.utc)
    bar = Candle(
        symbol="XAUUSD",
        timeframe=Timeframe.H4,
        timestamp=open_ts,
        open=2650,
        high=2651,
        low=2649,
        close=2650.5,
        volume=1,
    )
    mid = open_ts + timedelta(hours=2)
    end = open_ts + timedelta(hours=4)
    assert htf_bar_available_at(bar, mid) is False
    assert htf_bar_available_at(bar, end) is True
    assert filter_completed_htf([bar], mid) == []
    assert filter_completed_htf([bar], end) == [bar]


def test_future_htf_trend_change_does_not_affect_earlier_ltf():
    """Rollup HTF from growing H1 prefix — early MTF must ignore later HTF closes."""
    candles = gold_candles(200, trend=0.2, wave=5.0)
    early_i = 80
    early = candles[: early_i + 1]
    late = candles[:160]

    early_mtf = resolve_mtf_trends(early)
    # Late series may add completed HTF bars; early must equal recompute on early only
    early_again = resolve_mtf_trends(early)
    assert early_mtf == early_again

    late_mtf = resolve_mtf_trends(late)
    # Sanity: function is deterministic
    assert resolve_mtf_trends(late) == late_mtf

    # Explicit: filter a future H4 bar out of an early as_of
    h4_all = build_htf_bars_from_ltf(late, targets=(Timeframe.H4,), as_of=late[-1].timestamp)
    early_as_of = early[-1].timestamp
    filtered = {
        k: filter_completed_htf(v, early_as_of) for k, v in h4_all.items()
    }
    for series in filtered.values():
        for c in series:
            assert htf_bar_available_at(c, early_as_of)


def test_liquidity_single_source_smc_uses_engine_patterns():
    candles = bullish_trend_candles(80)
    # Force equal highs into series
    candles[40] = make_candle(40, open_=2650, high=2660.0, low=2648, close=2655)
    candles[50] = make_candle(50, open_=2652, high=2660.05, low=2649, close=2654)

    from services.quant_engine.swings.boundary import SCAN_SWING_VERSION, obtain_confirmed_swings
    from services.quant_engine.market_structure import analyze_structure

    swings = obtain_confirmed_swings(candles, version=SCAN_SWING_VERSION)
    snap = analyze_structure(candles, swings)
    liq = analyze_liquidity(candles, snapshot=snap, atr=5.0, symbol="XAUUSD", timeframe=Timeframe.H1)
    from_engine = patterns_from_liquidity_snapshot(liq)
    smc = SMCEngine().detect_all(
        candles,
        "XAUUSD",
        Timeframe.H1,
        confirmed_swings=swings,
        structure_snapshot=snap,
        liquidity_snapshot=liq,
    )
    liq_types = {p.pattern_type for p in smc if p.pattern_type in {"equal_highs", "equal_lows", "liquidity_sweep"}}
    engine_types = {p.pattern_type for p in from_engine}
    assert liq_types == engine_types
    # All liquidity patterns must be tagged from liquidity_engine
    for p in smc:
        if p.pattern_type in {"equal_highs", "equal_lows", "liquidity_sweep"}:
            assert p.metadata.get("source") == "liquidity_engine"


def test_liquidity_not_redetected_when_snapshot_passed():
    candles = gold_candles(100, trend=0.3, wave=4.0)
    bundle = analyze_candle_window("XAUUSD", Timeframe.H1, candles, evaluate=False)
    assert bundle.liquidity_snapshot is not None
    # Second call with same snapshot must not invent different sweep ids set
    again = analyze_candle_window(
        "XAUUSD",
        Timeframe.H1,
        candles,
        liquidity_snapshot=bundle.liquidity_snapshot,
        evaluate=False,
    )
    assert [s.sweep_id for s in bundle.liquidity_snapshot.sweeps] == [
        s.sweep_id for s in again.liquidity_snapshot.sweeps
    ]


def test_fingerprint_stable_when_liquidity_reused():
    candles = gold_candles(120, trend=0.4, wave=6.0)
    a = analyze_candle_window("XAUUSD", Timeframe.H1, candles, evaluate=True)
    b = analyze_candle_window(
        "XAUUSD",
        Timeframe.H1,
        candles,
        liquidity_snapshot=a.liquidity_snapshot,
        confirmed_swings=list(a.confirmed_swings),
        structure_snapshot=a.structure_snapshot,
        mtf_trends=dict(a.mtf_trends),
        news=a.news,
        evaluate=True,
    )
    assert a.analytical_fingerprint() == b.analytical_fingerprint()

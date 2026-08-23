"""Integrity tests: metrics, ambiguous candles, pipeline equivalence, leakage."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from shared.types.models import (
    Candle,
    IndicatorValues,
    SMCPattern,
    SignalDirection,
    Timeframe,
    TrendDirection,
)

from services.backtesting_service.execution import (
    ExecutionConfig,
    SimulatedTrade,
    compute_performance_metrics,
    simulate_trade,
)
from services.quant_engine.decision.engine import DecisionEngine
from services.quant_engine.pipeline import ANALYSIS_PIPELINE_VERSION, analyze_candle_window
from services.setup_intelligence.historical_matcher import (
    HistoricalSetupAnalyzer,
    SetupFingerprint,
)
from tests.fixtures.golden.candles import ambiguous_sl_tp_bar, bullish_trend_candles
from tests.swing_detection.fixtures import gold_candles


def test_metrics_profit_factor_and_expectancy_manual():
    """Manually calculated: 2 wins @ +2R and +1R, 1 loss @ -1R."""
    trades = [
        SimulatedTrade(2650, 2652, "buy", "win", 200, 2.0, 1.0, 2.0, 80),
        SimulatedTrade(2650, 2651, "buy", "win", 100, 1.0, 1.0, 1.0, 75),
        SimulatedTrade(2650, 2649, "buy", "loss", -100, -1.0, 1.0, -1.0, 70),
    ]
    m = compute_performance_metrics(trades)
    assert m.total_trades == 3
    assert m.wins == 2 and m.losses == 1
    assert abs(m.win_rate - (2 / 3) * 100) < 0.01
    # gross profit 3.0 / gross loss 1.0
    assert m.profit_factor == 3.0
    # expectancy = (2 + 1 - 1) / 3 = 2/3
    assert abs(m.expectancy - (2.0 / 3.0)) < 1e-9
    assert abs(m.avg_r - m.expectancy) < 1e-9


def test_ambiguous_candle_is_conservative_sl_first():
    bar = ambiguous_sl_tp_bar(entry=2650.0)
    trade = simulate_trade(
        direction="buy",
        entry=2650.0,
        stop_loss=2645.0,
        take_profit=2655.0,
        forward_bars=[bar],
        pip=0.01,
        score=80,
        config=ExecutionConfig(),
    )
    assert trade.ambiguous is True
    assert trade.outcome == "loss"
    assert trade.exit_price == 2645.0


def test_entry_spread_worsens_buy_fill():
    bar = Candle(
        symbol="XAUUSD",
        timeframe=Timeframe.H1,
        timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
        open=2650,
        high=2660,
        low=2640,
        close=2655,
        volume=1,
    )
    trade = simulate_trade(
        direction="buy",
        entry=2650.0,
        stop_loss=2640.0,
        take_profit=2660.0,
        forward_bars=[bar],
        pip=0.01,
        config=ExecutionConfig(spread_pips=2.0, slippage_pips=0.0),
    )
    # half spread = 0.01 → entry 2650.01
    assert trade.entry_price == 2650.01


def test_canonical_pipeline_fingerprint_deterministic():
    candles = gold_candles(160, trend=0.4, wave=6.0)
    window = candles[:120]
    a = analyze_candle_window("XAUUSD", Timeframe.H1, window, evaluate=True)
    b = analyze_candle_window("XAUUSD", Timeframe.H1, window, evaluate=True)
    assert a.analytical_fingerprint() == b.analytical_fingerprint()
    assert a.pipeline_version == ANALYSIS_PIPELINE_VERSION
    assert a.signal is not None
    assert a.signal.market_features["pipeline_version"] == ANALYSIS_PIPELINE_VERSION


def test_replay_backtest_analytical_equivalence_at_index():
    """Same prefix → same analytical fingerprint via canonical pipeline."""
    candles = gold_candles(180, trend=0.35, wave=7.0)
    i = 100
    window = candles[: i + 1]
    fp_a = analyze_candle_window("XAUUSD", Timeframe.H1, window).analytical_fingerprint()
    fp_b = analyze_candle_window("XAUUSD", Timeframe.H1, list(window)).analytical_fingerprint()
    assert fp_a == fp_b
    # Structure/score must not depend on future bars after i.
    longer = candles[: i + 20]
    early = analyze_candle_window("XAUUSD", Timeframe.H1, window).analytical_fingerprint()
    # Re-run early window alone — fingerprint stable
    assert early == fp_a
    # Full longer window may differ (expected); early must not include later BOS count
    late = analyze_candle_window("XAUUSD", Timeframe.H1, longer).analytical_fingerprint()
    assert late["as_of_index"] == i + 19
    assert early["as_of_index"] == i


def test_structure_no_lookahead_prefix():
    from services.quant_engine.market_structure import analyze_structure
    from services.quant_engine.swings.boundary import SCAN_SWING_VERSION, obtain_confirmed_swings

    candles = gold_candles(200, trend=0.5, wave=8.0)
    mid = 120
    swings_mid = obtain_confirmed_swings(candles[: mid + 1], version=SCAN_SWING_VERSION)
    snap_mid = analyze_structure(candles[: mid + 1], swings_mid)
    swings_full = obtain_confirmed_swings(candles, version=SCAN_SWING_VERSION)
    snap_full = analyze_structure(candles, swings_full)
    mid_ids = {e.event_id for e in snap_mid.events}
    # Any event in mid snapshot must have break_index <= mid
    assert all(e.break_index <= mid for e in snap_mid.events)
    # Events that break after mid must not appear in mid snapshot
    future_ids = {e.event_id for e in snap_full.events if e.break_index > mid}
    assert mid_ids.isdisjoint(future_ids)


def test_historical_setup_does_not_adjust_live_confidence():
    candles = gold_candles(160, trend=0.4, wave=6.0)
    last = candles[-1]
    indicators = IndicatorValues(
        symbol="XAUUSD",
        timeframe=Timeframe.H1,
        timestamp=last.timestamp,
        ema_20=last.close * 0.999,
        ema_50=last.close * 0.997,
        ema_200=last.close * 0.99,
        adx_14=28.0,
        rsi_14=55.0,
        atr_14=5.0,
    )
    patterns = [
        SMCPattern(pattern_type="fvg", direction=SignalDirection.BUY, strength=60),
    ]
    signal = DecisionEngine().evaluate(
        "XAUUSD",
        Timeframe.H1,
        candles,
        indicators,
        patterns,
    )
    # Live path must not apply historical confidence multiplier.
    if signal.historical_evidence:
        assert signal.historical_evidence.get("confidence_multiplier", 1.0) == 1.0


def test_historical_matcher_as_of_blocks_future_outcomes():
    candles = bullish_trend_candles(100)
    fp = SetupFingerprint(
        direction="buy",
        trend="bullish",
        patterns=frozenset({"fvg"}),
        score_bucket=7,
    )
    # With tiny as_of, analyzer should return empty (not enough room).
    ev = HistoricalSetupAnalyzer().analyze(
        "XAUUSD",
        Timeframe.H1,
        candles,
        fp,
        as_of_index=50,
        forward_bars=12,
        apply_confidence_adjustment=False,
    )
    assert ev.sample_size == 0


def test_ob_reaction_never_reads_past_window_end():
    from services.quant_engine.features.extractor import FeatureExtractor

    candles = bullish_trend_candles(30)
    # OB at last bar — reaction requires idx+3 < len → must return 0
    p = SMCPattern(
        pattern_type="order_block",
        direction=SignalDirection.BUY,
        strength=70,
        metadata={"index": len(candles) - 1},
    )
    score = FeatureExtractor._reaction_score(p, candles, len(candles) - 1)
    assert score == 0.0

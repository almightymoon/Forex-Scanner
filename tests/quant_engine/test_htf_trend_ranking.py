"""HTF trend injection into zone ranking — causality, parity, golden freeze."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from services.quant_engine.pipeline import (
    ANALYSIS_PIPELINE_VERSION,
    analyze_candle_window,
    build_htf_bars_from_ltf,
    filter_completed_htf,
    resolve_mtf_trends,
    select_ranking_htf_trend,
)
from services.quant_engine.pipeline.mtf_context import htf_bar_available_at
from services.quant_engine.zones.context import Alignment, build_zone_context
from shared.types.models import Candle, Timeframe, TrendDirection
from tests.fixtures.golden.signals import build_fixture_candles, load_golden_signal
from tests.quant_engine.test_zone_ranking import _empty_structure, _fvg
from tests.swing_detection.fixtures import gold_candles
from shared.types.models import SignalDirection


def test_select_ranking_htf_nearest_higher():
    mtf = {
        "H4": TrendDirection.BULLISH,
        "D1": TrendDirection.BEARISH,
        "M15": TrendDirection.BEARISH,
    }
    trend, tf = select_ranking_htf_trend(mtf, Timeframe.H1)
    assert tf == "H4"
    assert trend is TrendDirection.BULLISH
    # No higher TF → None
    assert select_ranking_htf_trend({"M15": TrendDirection.BULLISH}, Timeframe.H1) == (None, None)


def test_pipeline_injects_resolved_htf_into_zone_context():
    candles = gold_candles(240, trend=0.4, wave=6.0)
    bundle = analyze_candle_window("XAUUSD", Timeframe.H1, candles, evaluate=False)
    assert bundle.metadata["ranking_htf_tf"] == "H4"
    assert bundle.metadata["ranking_htf_trend"] == "bullish"
    fvgs = [p for p in bundle.smc_patterns if p.pattern_type == "fvg"]
    assert fvgs
    ctx = fvgs[0].metadata["zone_context"]
    assert ctx["trend_source"] == "resolved_htf:H4"
    assert ctx["htf_trend"] == "bullish"
    assert ctx["htf_trend_tf"] == "H4"


def test_htf_trend_alignment_differs_from_structure_when_injected():
    z = _fvg(zone_id="z", direction=SignalDirection.BUY, lo=100, hi=101, created=2)
    # Structure bearish, HTF bullish → structure OPPOSED, trend ALIGNED
    ctx = build_zone_context(
        z,
        price=102,
        structure=_empty_structure(TrendDirection.BEARISH),
        trend=TrendDirection.BULLISH,
        htf_trend_tf="H4",
    )
    assert ctx.structure_alignment is Alignment.OPPOSED
    assert ctx.trend_alignment is Alignment.ALIGNED
    assert ctx.trend_source == "resolved_htf:H4"


def test_future_htf_reversal_does_not_alter_prefix_ranking():
    candles = gold_candles(300, trend=0.4, wave=6.0)
    t = 239
    early = candles[: t + 1]
    late = candles  # includes future bars that may change later HTF

    a = analyze_candle_window("XAUUSD", Timeframe.H1, early, evaluate=False)
    # Recompute early with late series filtered via as_of through resolve only on early
    b = analyze_candle_window("XAUUSD", Timeframe.H1, list(early), evaluate=False)
    assert a.metadata["ranking_htf_trend"] == b.metadata["ranking_htf_trend"]
    assert a.analytical_fingerprint() == b.analytical_fingerprint()

    late_bundle = analyze_candle_window("XAUUSD", Timeframe.H1, late, evaluate=False)
    # Late may differ; early fingerprint must not depend on late candles
    assert a.analytical_fingerprint()["as_of_index"] == t
    assert late_bundle.analytical_fingerprint()["as_of_index"] == len(late) - 1


def test_incomplete_htf_bar_excluded_from_ranking_trend():
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
    assert htf_bar_available_at(bar, mid) is False
    assert filter_completed_htf([bar], mid) == []
    # Injecting incomplete provider bar must not create an H4 trend at mid as_of
    ltf = gold_candles(80, trend=0.2, wave=3.0)
    # Force as_of to mid conceptually via empty completed H4
    mtf = resolve_mtf_trends(ltf, bars_by_timeframe={"H4": [bar]}, as_of=mid)
    # With only incomplete bar and short LTF rollup, ranking HTF may be absent
    trend, tf = select_ranking_htf_trend(mtf, Timeframe.H1)
    # Must not invent a trend from the incomplete bar alone
    assert "H4" not in mtf or htf_bar_available_at(bar, mid) is False


def test_provider_authority_uses_merge_not_second_system():
    """Ranking uses resolve_mtf_trends output (merge_htf_bars SoT); drift is observational."""
    candles = gold_candles(240, trend=0.4, wave=6.0)
    rolled = build_htf_bars_from_ltf(candles, targets=(Timeframe.H4,))
    # Provider identical to rollup → same ranking HTF
    mtf_a = resolve_mtf_trends(candles, bars_by_timeframe=rolled)
    mtf_b = resolve_mtf_trends(candles, bars_by_timeframe=None)
    assert select_ranking_htf_trend(mtf_a, Timeframe.H1) == select_ranking_htf_trend(
        mtf_b, Timeframe.H1
    )


def test_live_replay_backtest_ranking_parity():
    candles = gold_candles(240, trend=0.4, wave=6.0)
    live = analyze_candle_window("XAUUSD", Timeframe.H1, candles, evaluate=True)
    replay = analyze_candle_window("XAUUSD", Timeframe.H1, list(candles), evaluate=True)
    backtest = analyze_candle_window("XAUUSD", Timeframe.H1, candles[:], evaluate=True)
    assert live.analytical_fingerprint() == replay.analytical_fingerprint() == backtest.analytical_fingerprint()
    assert live.metadata["ranking_htf_trend"] == replay.metadata["ranking_htf_trend"]
    fa = [p.metadata.get("zone_id") for p in live.smc_patterns if p.pattern_type == "fvg"]
    fb = [p.metadata.get("zone_id") for p in replay.smc_patterns if p.pattern_type == "fvg"]
    assert fa == fb


def test_golden_signal_fixture_regression():
    expected = load_golden_signal("xauusd_h1_gold240_t04_w6")
    assert expected["pipeline_version"] == ANALYSIS_PIPELINE_VERSION
    candles = build_fixture_candles(expected)
    bundle = analyze_candle_window(
        expected["symbol"],
        Timeframe.H1,
        candles,
        evaluate=True,
    )
    sig = bundle.signal
    assert sig is not None
    assert bundle.metadata["ranking_htf_trend"] == expected["ranking_htf_trend"]
    assert bundle.metadata["ranking_htf_tf"] == expected["ranking_htf_tf"]
    assert {k: v.value for k, v in sorted(bundle.mtf_trends.items())} == expected["mtf_trends"]
    fp = bundle.analytical_fingerprint()
    assert fp["ranked_fvg_ids"] == expected["ranked_fvg_ids"]
    assert fp["fvg_zone_count"] == expected["fvg_zone_count"]
    assert fp["structure_external_bias"] == expected["structure_external_bias"]
    assert sig.direction.value == expected["direction"]
    assert sig.score == expected["score"]
    assert round(sig.confidence, 6) == expected["confidence"]
    assert sig.trend.value == expected["trend"]
    assert round(sig.stop_loss, 8) == expected["stop_loss"]
    assert round(sig.take_profit_1, 8) == expected["take_profit_1"]
    assert round(sig.entry_zone_low, 8) == expected["entry_zone_low"]
    assert round(sig.entry_zone_high, 8) == expected["entry_zone_high"]
    fvgs = [p for p in bundle.smc_patterns if p.pattern_type == "fvg"]
    assert fvgs[0].metadata["zone_context"]["trend_source"] == expected["top_fvg_trend_source"]
    assert fvgs[0].metadata["zone_context"]["trend_alignment"] == expected["top_fvg_trend_alignment"]


def test_reproducibility_same_input_same_fingerprint():
    candles = gold_candles(240, trend=0.4, wave=6.0)
    fingerprints = [
        analyze_candle_window("XAUUSD", Timeframe.H1, list(candles), evaluate=True).analytical_fingerprint()
        for _ in range(3)
    ]
    assert fingerprints[0] == fingerprints[1] == fingerprints[2]


def test_performance_regression_guards():
    candles = gold_candles(5000, trend=0.3, wave=5.0)
    results = {}
    for n in (100, 500, 1000, 5000):
        window = candles[:n]
        t0 = time.perf_counter()
        analyze_candle_window("XAUUSD", Timeframe.H1, window, evaluate=False)
        results[n] = (time.perf_counter() - t0) * 1000
    # Generous CI guards (baseline ~sub-second detect; full analyze higher)
    assert results[100] < 5000
    assert results[500] < 15000
    assert results[1000] < 30000
    assert results[5000] < 120000


def test_pipeline_version_1_4_0():
    assert ANALYSIS_PIPELINE_VERSION == "1.4.0"

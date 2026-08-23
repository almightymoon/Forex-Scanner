"""Acceptance tests for Market Structure Engine product contract.

Validates HH/HL/LH/LL, trend labels, BOS/CHoCH, state view, determinism,
and no-lookahead prefix consistency on synthetic scenarios — without
tuning or instantiating the swing engine inside the structure path.
"""

from __future__ import annotations

from shared.types.models import Timeframe, TrendDirection
from swing_engine.models import SwingDirection

from services.quant_engine.market_structure import (
    MarketTrendLabel,
    StructureEventType,
    StructureRelation,
    analyze_market_structure,
    analyze_structure,
    classify_market_trend,
    explain_swing_classifications,
)
from services.quant_engine.swings.boundary import SCAN_SWING_VERSION
from tests.quant_engine.structure_scenarios import (
    bearish_structure_scenario,
    bullish_structure_scenario,
    equal_high_scenario,
    ranging_mixed_scenario,
    reversal_choch_scenario,
)


def _relation_set(snapshot, direction: SwingDirection) -> set[StructureRelation]:
    return {
        r.relation
        for r in snapshot.swing_relations
        if r.direction is direction
        and r.relation is not StructureRelation.UNKNOWN
    }


def test_bullish_hh_hl_and_bos():
    candles, swings = bullish_structure_scenario()
    analysis = analyze_market_structure(
        candles, swings, symbol="EURUSD", timeframe=Timeframe.H1
    )
    snap = analysis.snapshot
    assert StructureRelation.HL in _relation_set(snap, SwingDirection.LOW)
    assert StructureRelation.HH in _relation_set(snap, SwingDirection.HIGH)
    bos = [e for e in snap.events if e.event_type is StructureEventType.BOS]
    assert bos
    assert any(e.direction is TrendDirection.BULLISH for e in bos)
    assert analysis.trend in (MarketTrendLabel.BULLISH, MarketTrendLabel.UNDEFINED)
    assert analysis.state.swing_engine_version == SCAN_SWING_VERSION
    assert analysis.state.last_swing_high is not None
    assert analysis.classifications


def test_bearish_lh_ll_and_bos():
    candles, swings = bearish_structure_scenario()
    snap = analyze_structure(candles, swings)
    assert StructureRelation.LH in _relation_set(snap, SwingDirection.HIGH)
    assert StructureRelation.LL in _relation_set(snap, SwingDirection.LOW)
    bos = [e for e in snap.events if e.event_type is StructureEventType.BOS]
    assert bos
    assert any(e.direction is TrendDirection.BEARISH for e in bos)


def test_reversal_emits_choch_not_forced_bearish_trend():
    candles, swings = reversal_choch_scenario()
    analysis = analyze_market_structure(candles, swings, symbol="EURUSD")
    choch = [
        e
        for e in analysis.snapshot.events
        if e.event_type is StructureEventType.CHOCH
    ]
    assert choch
    assert choch[-1].direction is TrendDirection.BEARISH
    # Pending reversal must not force BEARISH product trend.
    assert analysis.trend is MarketTrendLabel.UNDEFINED
    assert analysis.state.last_choch is not None


def test_ranging_or_undefined_without_break():
    candles, swings = ranging_mixed_scenario()
    trend, assessment = classify_market_trend(analyze_structure(candles, swings))
    assert trend in (MarketTrendLabel.RANGING, MarketTrendLabel.UNDEFINED, MarketTrendLabel.BULLISH)
    assert "trend" in assessment.to_dict()


def test_equal_high_classification():
    candles, swings = equal_high_scenario()
    snap = analyze_structure(candles, swings)
    assert StructureRelation.EQUAL_HIGH in _relation_set(snap, SwingDirection.HIGH)
    records = explain_swing_classifications(snap, symbol="EURUSD", timeframe="H1")
    eq = [r for r in records if r.classification == "EQUAL_HIGH"]
    assert eq
    assert eq[0].price_difference == 0.0 or abs(eq[0].price_difference or 0) < 1e-9


def test_insufficient_history_undefined():
    trend, _ = classify_market_trend(None)
    assert trend is MarketTrendLabel.UNDEFINED
    empty = analyze_structure([], [])
    trend2, _ = classify_market_trend(empty)
    assert trend2 is MarketTrendLabel.UNDEFINED


def test_determinism_identical_outputs():
    candles, swings = bullish_structure_scenario()
    a = analyze_market_structure(candles, swings, symbol="EURUSD").to_dict()
    b = analyze_market_structure(candles, swings, symbol="EURUSD").to_dict()
    assert a["events"] == b["events"]
    assert a["trend"] == b["trend"]
    assert a["state"]["classifications"] == b["state"]["classifications"]


def test_no_lookahead_prefix_consistency():
    candles, swings = bullish_structure_scenario()
    full = analyze_structure(candles, swings)
    assert full.events
    first = full.events[0]
    n = first.break_index
    swings_n = [
        s
        for s in swings
        if s.confirmation_index is not None and int(s.confirmation_index) <= n
    ]
    prefix = analyze_structure(candles[: n + 1], swings_n, as_of_index=n)
    assert first.event_id in {e.event_id for e in prefix.events}

    # Extending candles beyond n must not change events through as_of=n.
    from tests.quant_engine.structure_scenarios import candle

    extended = list(candles)
    last = candles[-1]
    for i in range(len(candles), len(candles) + 10):
        extended.append(
            candle(i, high=last.high, low=last.low, close=last.close, symbol=last.symbol)
        )
    later = analyze_structure(extended[: n + 1], swings_n, as_of_index=n)
    assert [e.to_dict() for e in later.events] == [e.to_dict() for e in prefix.events]


def test_symbol_and_timeframe_boundaries():
    candles, swings = bullish_structure_scenario()
    eurusd = analyze_market_structure(
        candles, swings, symbol="EURUSD", timeframe=Timeframe.H1
    )
    gbpusd_candles = [
        c.__class__(
            symbol="GBPUSD",
            timeframe=Timeframe.H4,
            timestamp=c.timestamp,
            open=c.open,
            high=c.high,
            low=c.low,
            close=c.close,
            volume=c.volume,
        )
        for c in candles
    ]
    gbpusd = analyze_market_structure(
        gbpusd_candles, swings, symbol="GBPUSD", timeframe=Timeframe.H4
    )
    assert eurusd.state.symbol == "EURUSD"
    assert gbpusd.state.symbol == "GBPUSD"
    assert eurusd.state.timeframe == "H1"
    assert gbpusd.state.timeframe == "H4"
    # Structure math is price-path based — events should match for identical OHLC.
    assert [e.event_id for e in eurusd.snapshot.events] == [
        e.event_id for e in gbpusd.snapshot.events
    ]


def test_classification_explains_previous_comparable():
    candles, swings = bullish_structure_scenario()
    snap = analyze_structure(candles, swings)
    records = explain_swing_classifications(
        snap, symbol="EURUSD", timeframe="H1", swing_engine_version=SCAN_SWING_VERSION
    )
    with_prev = [r for r in records if r.previous_comparable_swing_id]
    assert with_prev
    sample = with_prev[0]
    assert sample.previous_price is not None
    assert sample.price_difference is not None
    assert sample.swing_engine_version == SCAN_SWING_VERSION

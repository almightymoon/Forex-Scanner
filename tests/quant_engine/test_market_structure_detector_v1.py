"""Focused tests for Market Structure Engine v1 causal detector."""

from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from shared.types.models import Candle, Timeframe, TrendDirection
from swing_engine import SwingEngine, get_config
from swing_engine.models import (
    DetectedSwing,
    SwingDirection,
    SwingScope,
    SwingTier,
)

from services.quant_engine.market_structure import (
    StructureDetectorConfig,
    StructureEventType,
    StructureInputError,
    StructureRelation,
    analyze_structure,
)
from services.quant_engine.market_structure import detector as detector_mod


ROOT = Path(__file__).resolve().parents[2]
DETECTOR_PATH = (
    ROOT / "services/quant_engine/market_structure/detector.py"
)


def _ts(index: int) -> datetime:
    return datetime(2025, 1, 1, tzinfo=timezone.utc) + timedelta(hours=index)


def _candle(
    index: int,
    *,
    high: float,
    low: float,
    close: float,
    open_: float | None = None,
) -> Candle:
    open_price = open_ if open_ is not None else (high + low) / 2.0
    return Candle(
        symbol="XAUUSD",
        timeframe=Timeframe.H1,
        timestamp=_ts(index),
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=100.0,
    )


def _swing(
    pivot: int,
    direction: SwingDirection,
    price: float,
    *,
    confirmation: int,
    tier: SwingTier = SwingTier.MAJOR,
    scope: SwingScope = SwingScope.EXTERNAL,
    hierarchy_confirmation: int | None = None,
) -> DetectedSwing:
    return DetectedSwing(
        timestamp=_ts(pivot),
        price=price,
        direction=direction,
        tier=tier,
        scope=scope,
        pivot_index=pivot,
        confirmed=True,
        confirmed_timestamp=_ts(confirmation),
        confirmation_index=confirmation,
        confirmation_delay=max(0, confirmation - pivot),
        strength=4,
        hierarchy_confirmation_index=hierarchy_confirmation,
    )


def test_empty_candles_and_swings():
    snap = analyze_structure([], [])
    assert snap.as_of_index == -1
    assert snap.events == ()
    assert snap.external_bias is TrendDirection.RANGING


def test_invalid_pivot_index_refusal():
    candles = [_candle(i, high=10, low=9, close=9.5) for i in range(5)]
    swings = [_swing(10, SwingDirection.HIGH, 10.0, confirmation=2)]
    with pytest.raises(StructureInputError, match="pivot_index"):
        analyze_structure(candles, swings, as_of_index=4)


def test_future_confirmation_refusal():
    candles = [_candle(i, high=10, low=9, close=9.5) for i in range(5)]
    swings = [_swing(1, SwingDirection.HIGH, 10.0, confirmation=4)]
    with pytest.raises(StructureInputError, match="confirmation_index"):
        analyze_structure(candles, swings, as_of_index=3)


def test_deterministic_input_ordering():
    candles = [_candle(i, high=12, low=8, close=10) for i in range(20)]
    a = _swing(2, SwingDirection.LOW, 8.0, confirmation=4)
    b = _swing(6, SwingDirection.HIGH, 12.0, confirmation=8)
    left = analyze_structure(candles, [b, a], as_of_index=19)
    right = analyze_structure(candles, [a, b], as_of_index=19)
    assert left.to_dict() == right.to_dict()


def test_high_relation_hh_and_lh():
    candles = [_candle(i, high=20, low=5, close=12) for i in range(30)]
    swings = [
        _swing(2, SwingDirection.HIGH, 10.0, confirmation=3),
        _swing(8, SwingDirection.HIGH, 12.0, confirmation=9),
        _swing(14, SwingDirection.HIGH, 11.0, confirmation=15),
    ]
    snap = analyze_structure(candles, swings, as_of_index=20)
    highs = [r for r in snap.swing_relations if r.direction is SwingDirection.HIGH]
    assert highs[0].relation is StructureRelation.UNKNOWN
    assert highs[1].relation is StructureRelation.HH
    assert highs[2].relation is StructureRelation.LH


def test_low_relation_hl_and_ll():
    candles = [_candle(i, high=20, low=5, close=12) for i in range(30)]
    swings = [
        _swing(2, SwingDirection.LOW, 10.0, confirmation=3),
        _swing(8, SwingDirection.LOW, 11.0, confirmation=9),
        _swing(14, SwingDirection.LOW, 9.0, confirmation=15),
    ]
    snap = analyze_structure(candles, swings, as_of_index=20)
    lows = [r for r in snap.swing_relations if r.direction is SwingDirection.LOW]
    assert lows[1].relation is StructureRelation.HL
    assert lows[2].relation is StructureRelation.LL


def test_equal_high_and_low_tolerance():
    cfg = StructureDetectorConfig(price_equality_tolerance=0.05)
    candles = [_candle(i, high=20, low=5, close=12) for i in range(30)]
    swings = [
        _swing(2, SwingDirection.HIGH, 10.00, confirmation=3),
        _swing(8, SwingDirection.HIGH, 10.04, confirmation=9),
        _swing(12, SwingDirection.LOW, 7.00, confirmation=13),
        _swing(16, SwingDirection.LOW, 7.03, confirmation=17),
    ]
    snap = analyze_structure(candles, swings, as_of_index=20, config=cfg)
    by_id = {r.swing_id: r for r in snap.swing_relations}
    assert by_id["HIGH:8"].relation is StructureRelation.EQUAL_HIGH
    assert by_id["LOW:16"].relation is StructureRelation.EQUAL_LOW


def test_internal_and_external_relation_tracks_separate():
    candles = [_candle(i, high=20, low=5, close=12) for i in range(30)]
    swings = [
        _swing(
            2,
            SwingDirection.HIGH,
            15.0,
            confirmation=3,
            tier=SwingTier.MAJOR,
            scope=SwingScope.EXTERNAL,
        ),
        _swing(
            6,
            SwingDirection.HIGH,
            12.0,
            confirmation=7,
            tier=SwingTier.MINOR,
            scope=SwingScope.INTERNAL,
        ),
    ]
    snap = analyze_structure(candles, swings, as_of_index=20)
    internal = next(
        r for r in snap.swing_relations if r.scope is SwingScope.INTERNAL
    )
    # Internal high is first on its track → UNKNOWN, not LH vs external 15.
    assert internal.relation is StructureRelation.UNKNOWN


def test_wick_only_high_break_emits_no_event():
    # Level high at 10 available at 2; candle wick above but close inside.
    candles = [
        _candle(0, high=9, low=8, close=8.5),
        _candle(1, high=9.5, low=8, close=9),
        _candle(2, high=9.2, low=8, close=8.8),
        _candle(3, high=11.0, low=8, close=9.5),  # wick > 10, close <= 10
        _candle(4, high=9.8, low=8, close=9.0),
    ]
    swings = [_swing(1, SwingDirection.HIGH, 10.0, confirmation=2)]
    snap = analyze_structure(candles, swings, as_of_index=4)
    assert snap.events == ()
    assert snap.external_bias is TrendDirection.RANGING


def test_close_above_high_emits_bullish_bos():
    candles = [
        _candle(0, high=9, low=8, close=8.5),
        _candle(1, high=9.5, low=8, close=9),
        _candle(2, high=9.2, low=8, close=8.8),
        _candle(3, high=11.0, low=8, close=10.5),  # close > 10
    ]
    swings = [_swing(1, SwingDirection.HIGH, 10.0, confirmation=2)]
    snap = analyze_structure(candles, swings, as_of_index=3)
    assert len(snap.events) == 1
    event = snap.events[0]
    assert event.event_type is StructureEventType.BOS
    assert event.direction is TrendDirection.BULLISH
    assert event.scope is SwingScope.EXTERNAL
    assert snap.external_bias is TrendDirection.BULLISH
    assert event.is_continuation is False


def test_wick_only_low_break_emits_no_event():
    candles = [
        _candle(0, high=12, low=10, close=11),
        _candle(1, high=12, low=9.5, close=10.5),
        _candle(2, high=12, low=9.8, close=10.2),
        _candle(3, high=12, low=8.5, close=10.1),  # wick < 9, close > 9
    ]
    swings = [_swing(1, SwingDirection.LOW, 9.0, confirmation=2)]
    snap = analyze_structure(candles, swings, as_of_index=3)
    assert snap.events == ()


def test_close_below_low_emits_bearish_bos():
    candles = [
        _candle(0, high=12, low=10, close=11),
        _candle(1, high=12, low=9.5, close=10.5),
        _candle(2, high=12, low=9.8, close=10.2),
        _candle(3, high=12, low=8.0, close=8.5),  # close < 9
    ]
    swings = [_swing(1, SwingDirection.LOW, 9.0, confirmation=2)]
    snap = analyze_structure(candles, swings, as_of_index=3)
    assert len(snap.events) == 1
    assert snap.events[0].event_type is StructureEventType.BOS
    assert snap.events[0].direction is TrendDirection.BEARISH
    assert snap.external_bias is TrendDirection.BEARISH


def test_one_break_event_per_level():
    candles = [
        _candle(0, high=9, low=8, close=8.5),
        _candle(1, high=9.5, low=8, close=9),
        _candle(2, high=9.2, low=8, close=8.8),
        _candle(3, high=11.0, low=8, close=10.5),
        _candle(4, high=12.0, low=8, close=11.0),
        _candle(5, high=13.0, low=8, close=12.0),
    ]
    swings = [_swing(1, SwingDirection.HIGH, 10.0, confirmation=2)]
    snap = analyze_structure(candles, swings, as_of_index=5)
    assert len(snap.events) == 1
    assert snap.events[0].break_index == 3


def _bullish_setup():
    """Build candles/swings that establish bullish bias then allow continuations."""

    candles = []
    for i in range(25):
        candles.append(_candle(i, high=20, low=5, close=12))
    # External high 10 confirmed at 2, broken by close at 3 → bullish BOS
    candles[3] = _candle(3, high=11, low=8, close=10.5)
    # Later external high 12 confirmed at 8
    candles[8] = _candle(8, high=12.2, low=9, close=11)
    # Break of 12 at index 12
    candles[12] = _candle(12, high=13, low=9, close=12.5)
    # Bearish CHOCH: external low 9 confirmed at 14, broken at 16
    candles[16] = _candle(16, high=12, low=7, close=8.5)
    # Confirm bearish with another low break at 20 (level 8 confirmed 18)
    candles[20] = _candle(20, high=11, low=6, close=7.5)
    swings = [
        _swing(1, SwingDirection.HIGH, 10.0, confirmation=2),
        _swing(6, SwingDirection.HIGH, 12.0, confirmation=8),
        _swing(10, SwingDirection.LOW, 9.0, confirmation=14),
        _swing(15, SwingDirection.LOW, 8.0, confirmation=18),
    ]
    return candles, swings


def test_bullish_continuation_bos():
    candles, swings = _bullish_setup()
    snap = analyze_structure(candles, swings[:2], as_of_index=12)
    assert snap.external_bias is TrendDirection.BULLISH
    cont = [e for e in snap.events if e.is_continuation]
    assert cont
    assert cont[0].event_type is StructureEventType.BOS
    assert cont[0].direction is TrendDirection.BULLISH


def test_bearish_continuation_bos_and_choch_pending():
    candles, swings = _bullish_setup()
    # Through CHOCH only
    snap = analyze_structure(candles, swings[:3], as_of_index=16)
    choch = [e for e in snap.events if e.event_type is StructureEventType.CHOCH]
    assert choch
    assert snap.external_bias is TrendDirection.BULLISH
    assert snap.pending_external_bias is TrendDirection.BEARISH


def test_choch_does_not_immediately_confirm_opposite_bias():
    candles, swings = _bullish_setup()
    snap = analyze_structure(candles, swings[:3], as_of_index=16)
    assert snap.external_bias is TrendDirection.BULLISH
    assert snap.pending_external_bias is TrendDirection.BEARISH


def test_subsequent_opposite_bos_confirms_new_bias():
    candles, swings = _bullish_setup()
    snap = analyze_structure(candles, swings, as_of_index=20)
    assert snap.external_bias is TrendDirection.BEARISH
    assert snap.pending_external_bias is TrendDirection.RANGING
    confirms = [
        e
        for e in snap.events
        if e.event_type is StructureEventType.BOS
        and e.direction is TrendDirection.BEARISH
        and e.prior_bias is TrendDirection.BULLISH
        and e.pending_bias is TrendDirection.RANGING
        and e.resulting_bias is TrendDirection.BEARISH
    ]
    assert confirms


def test_pending_reversal_cancellation():
    candles = [_candle(i, high=20, low=5, close=12) for i in range(30)]
    # Establish bullish
    candles[3] = _candle(3, high=11, low=8, close=10.5)
    # CHOCH bearish pending via low break
    candles[10] = _candle(10, high=12, low=7, close=8.5)
    # Cancel with bullish continuation break of a new high
    candles[16] = _candle(16, high=14, low=8, close=13.5)
    swings = [
        _swing(1, SwingDirection.HIGH, 10.0, confirmation=2),
        _swing(6, SwingDirection.LOW, 9.0, confirmation=8),
        _swing(12, SwingDirection.HIGH, 13.0, confirmation=14),
    ]
    snap = analyze_structure(candles, swings, as_of_index=16)
    assert snap.external_bias is TrendDirection.BULLISH
    assert snap.pending_external_bias is TrendDirection.RANGING
    cancel = [
        e
        for e in snap.events
        if e.is_continuation and e.direction is TrendDirection.BULLISH
    ]
    assert cancel


def test_internal_event_does_not_alter_external_bias():
    candles = [_candle(i, high=20, low=5, close=12) for i in range(20)]
    candles[5] = _candle(5, high=11, low=8, close=10.5)
    swings = [
        _swing(
            2,
            SwingDirection.HIGH,
            10.0,
            confirmation=3,
            tier=SwingTier.MINOR,
            scope=SwingScope.INTERNAL,
        ),
    ]
    snap = analyze_structure(candles, swings, as_of_index=5)
    assert snap.external_bias is TrendDirection.RANGING
    assert snap.internal_bias is TrendDirection.BULLISH
    assert all(e.scope is SwingScope.INTERNAL for e in snap.events)


def test_stable_event_ids_and_serialized_output():
    candles = [
        _candle(0, high=9, low=8, close=8.5),
        _candle(1, high=9.5, low=8, close=9),
        _candle(2, high=9.2, low=8, close=8.8),
        _candle(3, high=11.0, low=8, close=10.5),
    ]
    swings = [_swing(1, SwingDirection.HIGH, 10.0, confirmation=2)]
    a = analyze_structure(candles, swings, as_of_index=3)
    b = analyze_structure(candles, swings, as_of_index=3)
    assert a.events[0].event_id == (
        "EXTERNAL:BOS:bullish:1:3"
    )
    assert a.to_dict() == b.to_dict()


def test_prefix_reproducibility():
    candles, swings = _bullish_setup()
    full = analyze_structure(candles, swings, as_of_index=20)
    n = 16
    prefix_events = [e for e in full.events if e.break_index <= n]
    # Swings available by N only.
    swings_n = [
        s
        for s in swings
        if s.confirmation_index is not None and s.confirmation_index <= n
    ]
    direct = analyze_structure(candles[: n + 1], swings_n, as_of_index=n)
    assert [e.to_dict() for e in prefix_events] == [
        e.to_dict() for e in direct.events
    ]


def test_core_detector_source_has_no_swing_engine_or_get_config():
    source = DETECTOR_PATH.read_text(encoding="utf-8")
    assert "SwingEngine" not in source
    assert "get_config" not in source
    assert "from swing_engine.models import" in source
    assert "SwingEngine" not in inspect.getsource(detector_mod)


def test_integration_v23_confirmed_swings_synthetic_prefix():
    from tests.swing_detection.fixtures import gold_candles

    candles = gold_candles(180, wave=10.0, trend=0.04, period=16, seed=3)
    config = get_config(Timeframe.H1, version="2.3.0", symbol="XAUUSD")
    result = SwingEngine(config, version="2.3.0").detect(
        candles,
        symbol="XAUUSD",
        timeframe=Timeframe.H1,
    )
    confirmed = list(result.confirmed_swings)
    assert confirmed
    snap = analyze_structure(
        candles,
        confirmed,
        as_of_index=len(candles) - 1,
    )
    assert snap.as_of_index == len(candles) - 1
    assert isinstance(snap.external_bias, TrendDirection)
    # Re-run deterministically
    again = analyze_structure(candles, confirmed, as_of_index=len(candles) - 1)
    assert snap.to_dict() == again.to_dict()


def test_legacy_public_imports_still_available():
    from services.quant_engine.market_structure import (
        MarketStructureEngine,
        StructureQuality,
        score_structure_event,
    )

    assert MarketStructureEngine is not None
    assert StructureQuality is not None
    assert callable(score_structure_event)


# --- Blocker 1: monotonic hierarchy availability ---


def test_hierarchy_projection_dual_phase_and_monotonic_availability():
    from services.quant_engine.market_structure import (
        project_swing_facts,
        structural_available_index,
    )

    swing = _swing(
        3,
        SwingDirection.HIGH,
        10.0,
        confirmation=5,
        tier=SwingTier.MAJOR,
        scope=SwingScope.EXTERNAL,
        hierarchy_confirmation=10,
    )
    assert structural_available_index(swing) == 5
    facts = project_swing_facts(swing)
    assert len(facts) == 2
    assert facts[0].scope is SwingScope.INTERNAL
    assert facts[0].tier is SwingTier.MINOR
    assert facts[0].available_index == 5
    assert facts[1].scope is SwingScope.EXTERNAL
    assert facts[1].tier is SwingTier.MAJOR
    assert facts[1].available_index == 10
    # Availability is fixed — not a function of as_of_index.
    assert facts[0].available_index == 5
    assert facts[1].available_index == 10


def test_hierarchy_boundary_prefix_reproducibility():
    """Through index 9, longer-prefix analysis must match prefix-9 analysis."""

    candles = [_candle(i, high=12, low=8, close=10) for i in range(20)]
    # Keep closes inside the level so hierarchy projection is isolated.
    swing = _swing(
        3,
        SwingDirection.HIGH,
        10.0,
        confirmation=5,
        tier=SwingTier.MAJOR,
        scope=SwingScope.EXTERNAL,
        hierarchy_confirmation=10,
    )
    short = analyze_structure(candles[:10], [swing], as_of_index=9)
    long = analyze_structure(candles, [swing], as_of_index=9)
    assert [r.to_dict() for r in short.swing_relations] == [
        r.to_dict() for r in long.swing_relations
    ]
    assert [e.to_dict() for e in short.events] == [
        e.to_dict() for e in long.events
    ]
    # Only first-level INTERNAL fact is visible before hierarchy confirmation.
    assert len(short.swing_relations) == 1
    assert short.swing_relations[0].scope is SwingScope.INTERNAL
    assert short.swing_relations[0].available_index == 5

    after = analyze_structure(candles, [swing], as_of_index=10)
    scopes = {r.scope for r in after.swing_relations}
    assert SwingScope.INTERNAL in scopes
    assert SwingScope.EXTERNAL in scopes
    # Extending as_of must not rewrite the earlier INTERNAL fact.
    internal = next(
        r for r in after.swing_relations if r.scope is SwingScope.INTERNAL
    )
    assert internal.available_index == 5
    assert internal.to_dict() == short.swing_relations[0].to_dict()


def test_hierarchy_external_not_consumed_before_confirmation():
    candles = [_candle(i, high=12, low=8, close=10) for i in range(12)]
    candles[7] = _candle(7, high=11, low=8, close=10.5)  # would break 10 if external
    swing = _swing(
        3,
        SwingDirection.HIGH,
        10.0,
        confirmation=5,
        tier=SwingTier.MAJOR,
        scope=SwingScope.EXTERNAL,
        hierarchy_confirmation=10,
    )
    snap = analyze_structure(candles, [swing], as_of_index=9)
    # Break at 7 is against INTERNAL first-level level (available at 5).
    assert snap.external_bias is TrendDirection.RANGING
    assert snap.internal_bias is TrendDirection.BULLISH


# --- Blocker 2: same-candle activation / break ---


def test_confirmation_candle_close_beyond_level_emits_no_event():
    candles = [
        _candle(0, high=9, low=8, close=8.5),
        _candle(1, high=9.5, low=8, close=9),
        _candle(2, high=11.0, low=8, close=10.5),  # confirmation candle
        _candle(3, high=9.8, low=8, close=9.0),
    ]
    swings = [_swing(1, SwingDirection.HIGH, 10.0, confirmation=2)]
    snap = analyze_structure(candles, swings, as_of_index=3)
    assert snap.events == ()
    assert snap.external_bias is TrendDirection.RANGING


def test_candle_after_confirmation_close_beyond_emits_event():
    candles = [
        _candle(0, high=9, low=8, close=8.5),
        _candle(1, high=9.5, low=8, close=9),
        _candle(2, high=11.0, low=8, close=10.5),  # activate only
        _candle(3, high=11.0, low=8, close=10.5),  # first valid break
    ]
    swings = [_swing(1, SwingDirection.HIGH, 10.0, confirmation=2)]
    snap = analyze_structure(candles, swings, as_of_index=3)
    assert len(snap.events) == 1
    assert snap.events[0].break_index == 3
    assert snap.events[0].level_available_index == 2


def test_wick_only_still_no_event_after_same_candle_rule():
    candles = [
        _candle(0, high=9, low=8, close=8.5),
        _candle(1, high=9.5, low=8, close=9),
        _candle(2, high=9.2, low=8, close=8.8),
        _candle(3, high=11.0, low=8, close=9.5),  # wick only after available
    ]
    swings = [_swing(1, SwingDirection.HIGH, 10.0, confirmation=2)]
    snap = analyze_structure(candles, swings, as_of_index=3)
    assert snap.events == ()


def test_hierarchy_promotion_same_candle_cannot_break():
    candles = [_candle(i, high=12, low=8, close=10) for i in range(14)]
    candles[10] = _candle(10, high=11, low=8, close=10.5)  # hierarchy avail candle
    candles[11] = _candle(11, high=11, low=8, close=10.5)  # first valid external break
    swing = _swing(
        3,
        SwingDirection.HIGH,
        10.0,
        confirmation=5,
        tier=SwingTier.MAJOR,
        scope=SwingScope.EXTERNAL,
        hierarchy_confirmation=10,
    )
    # Neutralize internal break by keeping closes <= 10 until hierarchy.
    for i in range(6, 10):
        candles[i] = _candle(i, high=10.0, low=8, close=9.5)
    snap_at_hier = analyze_structure(candles, [swing], as_of_index=10)
    ext_events = [e for e in snap_at_hier.events if e.scope is SwingScope.EXTERNAL]
    assert not ext_events
    snap_after = analyze_structure(candles, [swing], as_of_index=11)
    ext_events = [e for e in snap_after.events if e.scope is SwingScope.EXTERNAL]
    assert len(ext_events) == 1
    assert ext_events[0].break_index == 11
    assert ext_events[0].level_available_index == 10


# --- Blocker 3: atomic multi-level breaks ---


def test_multiple_highs_one_candle_one_bullish_event():
    candles = [_candle(i, high=20, low=5, close=9.5) for i in range(15)]
    candles[8] = _candle(8, high=16, low=8, close=15.5)  # crosses 10 and 12
    swings = [
        _swing(1, SwingDirection.HIGH, 10.0, confirmation=2),
        _swing(4, SwingDirection.HIGH, 12.0, confirmation=5),
    ]
    snap = analyze_structure(candles, swings, as_of_index=8)
    bullish = [e for e in snap.events if e.direction is TrendDirection.BULLISH]
    assert len(bullish) == 1
    assert bullish[0].break_index == 8
    assert bullish[0].level_price == 12.0  # highest crossed
    assert set(bullish[0].metadata["retired_level_swing_ids"]) == {
        "HIGH:1",
        "HIGH:4",
    }


def test_multiple_lows_one_candle_one_bearish_event():
    candles = [_candle(i, high=20, low=5, close=12) for i in range(15)]
    candles[8] = _candle(8, high=12, low=6, close=7.5)  # crosses 10 and 9
    swings = [
        _swing(1, SwingDirection.LOW, 10.0, confirmation=2),
        _swing(4, SwingDirection.LOW, 9.0, confirmation=5),
    ]
    snap = analyze_structure(candles, swings, as_of_index=8)
    bearish = [e for e in snap.events if e.direction is TrendDirection.BEARISH]
    assert len(bearish) == 1
    assert bearish[0].level_price == 9.0  # lowest crossed
    assert set(bearish[0].metadata["retired_level_swing_ids"]) == {
        "LOW:1",
        "LOW:4",
    }


def test_one_candle_cannot_emit_choch_and_confirming_bos():
    candles = [_candle(i, high=20, low=5, close=12) for i in range(25)]
    # Establish bullish via high 10.
    candles[3] = _candle(3, high=11, low=8, close=10.5)
    # One candle crosses two lows — previously could CHOCH then confirm.
    candles[12] = _candle(12, high=12, low=6, close=7.5)
    swings = [
        _swing(1, SwingDirection.HIGH, 10.0, confirmation=2),
        _swing(6, SwingDirection.LOW, 9.0, confirmation=8),
        _swing(9, SwingDirection.LOW, 8.0, confirmation=10),
    ]
    snap = analyze_structure(candles, swings, as_of_index=12)
    at_12 = [e for e in snap.events if e.break_index == 12]
    assert len(at_12) == 1
    assert at_12[0].event_type is StructureEventType.CHOCH
    assert snap.external_bias is TrendDirection.BULLISH
    assert snap.pending_external_bias is TrendDirection.BEARISH


def test_later_candle_confirms_reversal_after_atomic_choch():
    candles = [_candle(i, high=20, low=5, close=12) for i in range(25)]
    candles[3] = _candle(3, high=11, low=8, close=10.5)
    candles[12] = _candle(12, high=12, low=6, close=7.5)
    candles[18] = _candle(18, high=11, low=5, close=6.5)
    swings = [
        _swing(1, SwingDirection.HIGH, 10.0, confirmation=2),
        _swing(6, SwingDirection.LOW, 9.0, confirmation=8),
        _swing(9, SwingDirection.LOW, 8.0, confirmation=10),
        _swing(14, SwingDirection.LOW, 7.0, confirmation=16),
    ]
    snap = analyze_structure(candles, swings, as_of_index=18)
    assert snap.external_bias is TrendDirection.BEARISH
    assert snap.pending_external_bias is TrendDirection.RANGING
    confirms = [
        e
        for e in snap.events
        if e.break_index == 18 and e.event_type is StructureEventType.BOS
    ]
    assert confirms


def test_crossed_levels_retired_no_later_duplicates():
    candles = [_candle(i, high=20, low=5, close=9.5) for i in range(15)]
    candles[8] = _candle(8, high=16, low=8, close=15.5)
    candles[10] = _candle(10, high=16, low=8, close=15.5)
    swings = [
        _swing(1, SwingDirection.HIGH, 10.0, confirmation=2),
        _swing(4, SwingDirection.HIGH, 12.0, confirmation=5),
    ]
    snap = analyze_structure(candles, swings, as_of_index=10)
    assert len(snap.events) == 1
    assert snap.events[0].break_index == 8


# --- Input validation hardening ---


def test_reject_bool_nan_inf_swing_prices():
    candles = [_candle(i, high=10, low=9, close=9.5) for i in range(5)]
    for bad in (True, float("nan"), float("inf"), float("-inf")):
        swings = [_swing(1, SwingDirection.HIGH, bad, confirmation=2)]
        with pytest.raises(StructureInputError, match="invalid price"):
            analyze_structure(candles, swings, as_of_index=4)


def test_reject_non_finite_candle_close():
    candles = [_candle(i, high=10, low=9, close=9.5) for i in range(5)]
    candles[3] = _candle(3, high=10, low=9, close=float("nan"))
    swings = [_swing(1, SwingDirection.HIGH, 10.0, confirmation=2)]
    with pytest.raises(StructureInputError, match="non-finite candle close"):
        analyze_structure(candles, swings, as_of_index=4)


def test_reject_invalid_equality_tolerance():
    with pytest.raises(ValueError):
        StructureDetectorConfig(price_equality_tolerance=-0.1)
    with pytest.raises(ValueError):
        StructureDetectorConfig(price_equality_tolerance=float("nan"))


def test_reject_confirmation_before_pivot():
    candles = [_candle(i, high=10, low=9, close=9.5) for i in range(5)]
    swings = [_swing(3, SwingDirection.HIGH, 10.0, confirmation=2)]
    with pytest.raises(StructureInputError, match="earlier than pivot_index"):
        analyze_structure(candles, swings, as_of_index=4)


def test_reject_malformed_tier_and_scope():
    candles = [_candle(i, high=10, low=9, close=9.5) for i in range(5)]
    bad_tier = _swing(1, SwingDirection.HIGH, 10.0, confirmation=2)
    object.__setattr__(bad_tier, "tier", "MAJOR")  # type: ignore[misc]
    with pytest.raises(StructureInputError, match="invalid tier"):
        analyze_structure(candles, [bad_tier], as_of_index=4)

    bad_scope = _swing(1, SwingDirection.HIGH, 10.0, confirmation=2)
    object.__setattr__(bad_scope, "scope", "EXTERNAL")  # type: ignore[misc]
    with pytest.raises(StructureInputError, match="invalid scope"):
        analyze_structure(candles, [bad_scope], as_of_index=4)


def test_empty_candles_reject_noncanonical_as_of():
    with pytest.raises(StructureInputError, match="empty candles"):
        analyze_structure([], [], as_of_index=0)
    snap = analyze_structure([], [], as_of_index=-1)
    assert snap.as_of_index == -1

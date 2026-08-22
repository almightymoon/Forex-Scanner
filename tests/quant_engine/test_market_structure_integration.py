"""Tests for Market Structure Engine v1 → MarketFeatures adapter."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from shared.types.models import Candle, Timeframe, TrendDirection
from swing_engine.models import DetectedSwing, SwingDirection, SwingScope, SwingTier

from services.quant_engine.market_structure import (
    analyze_structure,
    structure_snapshot_to_features,
)
from services.quant_engine.market_structure.integration import (
    build_market_structure_state,
    build_trend_context_from_structure,
)
from services.quant_engine.market_structure.models import StructureEventType


def _ts(index: int) -> datetime:
    return datetime(2025, 1, 1, tzinfo=timezone.utc) + timedelta(hours=index)


def _candle(index: int, *, high: float, low: float, close: float) -> Candle:
    return Candle(
        symbol="XAUUSD",
        timeframe=Timeframe.H1,
        timestamp=_ts(index),
        open=(high + low) / 2.0,
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
) -> DetectedSwing:
    return DetectedSwing(
        timestamp=_ts(pivot),
        price=price,
        direction=direction,
        tier=tier,
        scope=scope,
        pivot_index=pivot,
        confirmed=True,
        confirmation_index=confirmation,
        confirmation_delay=max(0, confirmation - pivot),
        score=70.0,
    )


def test_snapshot_maps_into_feature_fields():
    candles = [_candle(i, high=12, low=8, close=10) for i in range(8)]
    candles[3] = _candle(3, high=11, low=8, close=10.5)
    swings = [_swing(1, SwingDirection.HIGH, 10.0, confirmation=2)]
    snap = analyze_structure(candles, swings, as_of_index=3)
    mapped = structure_snapshot_to_features(snap, confirmed_swings=swings)

    assert mapped["external_bias"] is TrendDirection.BULLISH
    assert mapped["pending_external_bias"] is TrendDirection.RANGING
    assert mapped["internal_bias"] is TrendDirection.RANGING
    assert mapped["last_structure_event"] == "bos"
    assert mapped["structure_continuation"] is False
    assert mapped["bos_kind"] == "external"
    assert mapped["swing_count"] == 1
    assert mapped["latest_structure_event_id"] == snap.events[0].event_id
    assert mapped["structure_event_ids"] == [snap.events[0].event_id]
    assert mapped["latest_bos_choch"]["event_type"] == StructureEventType.BOS.value
    assert mapped["structure_metadata"]["detector"] == "market_structure_v1"


def test_pending_external_reversal_maps():
    candles = [_candle(i, high=20, low=5, close=12) for i in range(20)]
    candles[3] = _candle(3, high=11, low=8, close=10.5)
    candles[10] = _candle(10, high=12, low=7, close=8.5)
    swings = [
        _swing(1, SwingDirection.HIGH, 10.0, confirmation=2),
        _swing(6, SwingDirection.LOW, 9.0, confirmation=8),
    ]
    snap = analyze_structure(candles, swings, as_of_index=10)
    mapped = structure_snapshot_to_features(snap, confirmed_swings=swings)
    assert mapped["external_bias"] is TrendDirection.BULLISH
    assert mapped["pending_external_bias"] is TrendDirection.BEARISH
    assert mapped["last_structure_event"] == "choch"
    assert mapped["structure_continuation"] is False


def test_internal_bias_does_not_overwrite_external():
    candles = [_candle(i, high=20, low=5, close=12) for i in range(12)]
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
    mapped = structure_snapshot_to_features(snap, confirmed_swings=swings)
    assert mapped["external_bias"] is TrendDirection.RANGING
    assert mapped["internal_bias"] is TrendDirection.BULLISH
    state = build_market_structure_state(snap, swings)
    assert state.direction is TrendDirection.RANGING


def test_trend_context_built_without_legacy_structure():
    candles = [_candle(i, high=12, low=8, close=10) for i in range(25)]
    candles[3] = _candle(3, high=11, low=8, close=10.5)
    swings = [_swing(1, SwingDirection.HIGH, 10.0, confirmation=2)]
    snap = analyze_structure(candles, swings, as_of_index=20)
    ctx = build_trend_context_from_structure(
        snap, candles, ema20=10.2, ema50=9.5, confirmed_swings=swings
    )
    assert ctx.direction is TrendDirection.BULLISH
    assert ctx.structure is not None
    assert ctx.structure.last_event == "bos"


def test_legacy_engine_run_from_snapshot_path():
    from services.quant_engine.market_structure import MarketStructureEngine
    from shared.types.models import SMCPattern, SignalDirection

    candles = [_candle(i, high=12, low=8, close=10) for i in range(8)]
    candles[3] = _candle(3, high=11, low=8, close=10.5)
    swings = [_swing(1, SwingDirection.HIGH, 10.0, confirmation=2)]
    patterns = [
        SMCPattern(pattern_type="bos", direction=SignalDirection.BUY, strength=80),
    ]
    out = MarketStructureEngine().run_from_confirmed_swings(
        candles, swings, patterns
    )
    assert out.name == "Market Structure"
    assert out.score > 0
    assert out.metadata["external_bias"] == TrendDirection.BULLISH.value

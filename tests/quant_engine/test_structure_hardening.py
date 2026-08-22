"""Tests for live-safe structure scoring and StructureSnapshot regime consumer."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from shared.types.models import Candle, SMCPattern, SignalDirection, Timeframe, TrendDirection
from swing_engine.models import DetectedSwing, SwingDirection, SwingScope, SwingTier

from services.quant_engine.market_structure import (
    StructureRegime,
    analyze_structure,
    classify_structure_regime,
    score_structure_event,
)
from services.quant_engine.swings.boundary import SCAN_SWING_VERSION


def _ts(i: int) -> datetime:
    return datetime(2025, 1, 1, tzinfo=timezone.utc) + timedelta(hours=i)


def _candle(i: int, *, high: float, low: float, close: float) -> Candle:
    return Candle(
        symbol="SYN",
        timeframe=Timeframe.H1,
        timestamp=_ts(i),
        open=(high + low) / 2,
        high=high,
        low=low,
        close=close,
        volume=100.0,
    )


def _swing(pivot: int, direction: SwingDirection, price: float, confirmation: int) -> DetectedSwing:
    return DetectedSwing(
        timestamp=_ts(pivot),
        price=price,
        direction=direction,
        tier=SwingTier.MAJOR,
        scope=SwingScope.EXTERNAL,
        pivot_index=pivot,
        confirmed=True,
        confirmation_index=confirmation,
        score=80.0,
    )


def test_scan_version_is_explicit_2_3_0():
    assert SCAN_SWING_VERSION == "2.3.0"


def test_live_scoring_does_not_use_future_candles():
    candles = [_candle(i, high=12, low=8, close=10) for i in range(20)]
    # Break at index 10; later candles explode upward (would inflate follow-through).
    candles[10] = _candle(10, high=11, low=8, close=10.5)
    for i in range(11, 20):
        candles[i] = _candle(i, high=20, low=15, close=19)

    pattern = SMCPattern(
        pattern_type="bos",
        direction=SignalDirection.BUY,
        strength=80,
        price_high=10.0,
        metadata={"break_index": 10, "swing_strength": 80},
    )
    live = score_structure_event(pattern, candles, atr=1.0, allow_lookahead=False)
    offline = score_structure_event(pattern, candles, atr=1.0, allow_lookahead=True)

    assert live.lookahead_used is False
    assert live.follow_through == 0.0
    assert offline.lookahead_used is True
    assert offline.follow_through > live.follow_through


def test_live_scoring_respects_as_of_index():
    candles = [_candle(i, high=12, low=8, close=10) for i in range(15)]
    candles[5] = _candle(5, high=11, low=8, close=10.5)
    pattern = SMCPattern(
        pattern_type="bos",
        direction=SignalDirection.BUY,
        price_high=10.0,
        metadata={"break_index": 5, "swing_strength": 70},
    )
    q = score_structure_event(
        pattern, candles, atr=1.0, allow_lookahead=False, as_of_index=5
    )
    assert q.overall >= 0
    assert q.lookahead_used is False


def test_regime_trending_bullish_from_snapshot():
    candles = [_candle(i, high=20, low=5, close=12) for i in range(20)]
    candles[3] = _candle(3, high=11, low=8, close=10.5)
    candles[12] = _candle(12, high=13, low=9, close=12.5)
    swings = [
        _swing(1, SwingDirection.HIGH, 10.0, 2),
        _swing(6, SwingDirection.HIGH, 12.0, 8),
    ]
    snap = analyze_structure(candles, swings)
    assessment = classify_structure_regime(snap)
    assert assessment.regime is StructureRegime.TRENDING_BULLISH
    assert assessment.external_bias is TrendDirection.BULLISH
    assert assessment.confidence > 0.4


def test_regime_reversal_pending():
    candles = [_candle(i, high=20, low=5, close=12) for i in range(20)]
    candles[3] = _candle(3, high=11, low=8, close=10.5)
    candles[10] = _candle(10, high=12, low=7, close=8.5)
    swings = [
        _swing(1, SwingDirection.HIGH, 10.0, 2),
        _swing(6, SwingDirection.LOW, 9.0, 8),
    ]
    snap = analyze_structure(candles, swings)
    assessment = classify_structure_regime(snap)
    assert assessment.regime is StructureRegime.REVERSAL_PENDING
    assert assessment.pending_external_bias is TrendDirection.BEARISH


def test_v23_cutover_on_gold_fixture():
    from tests.swing_detection.fixtures import gold_candles
    from services.quant_engine.swings.boundary import obtain_confirmed_swings
    from services.quant_engine.features.extractor import FeatureExtractor
    from tests.helpers import indicators

    cs = gold_candles(150, wave=10.0, trend=0.04, period=16, seed=7)
    swings = obtain_confirmed_swings(cs, version="2.3.0")
    assert swings
    features = FeatureExtractor(swing_version="2.3.0").extract(
        cs,
        indicators(symbol=cs[0].symbol, ema_20=2350, ema_50=2340, atr_14=5),
        [],
        confirmed_swings=swings,
    )
    assert features.swing_count == len(swings)
    assert features.structure_metadata.get("swing_version") == "2.3.0"
    assert features.structure_regime_assessment

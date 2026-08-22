"""TrendEngine integration with Market Structure Engine v1."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from shared.config.scoring_loader import get_v2_scoring_config
from shared.types.models import Candle, Timeframe, TrendDirection
from swing_engine.models import DetectedSwing, SwingDirection, SwingScope, SwingTier

from tests.helpers import indicators as make_indicators

from services.quant_engine.features.extractor import FeatureExtractor
from services.quant_engine.features.types import MarketFeatures
from services.quant_engine.market_structure import analyze_structure
from services.quant_engine.market_structure.integration import (
    build_trend_context_from_structure,
    structure_snapshot_to_features,
)
from services.quant_engine.trend.engine import TrendEngine


TREND_PATH = (
    Path(__file__).resolve().parents[2]
    / "services/quant_engine/trend/engine.py"
)


def _ts(index: int) -> datetime:
    return datetime(2025, 1, 1, tzinfo=timezone.utc) + timedelta(hours=index)


def _candle(index: int, *, high: float, low: float, close: float) -> Candle:
    return Candle(
        symbol="SYN",
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


def _features_from_swings(candles, swings) -> MarketFeatures:
    snap = analyze_structure(candles, swings, as_of_index=len(candles) - 1)
    mapped = structure_snapshot_to_features(snap, confirmed_swings=swings)
    ctx = build_trend_context_from_structure(
        snap, candles, ema20=10.2, ema50=9.5, confirmed_swings=swings
    )
    features = MarketFeatures()
    for key, value in mapped.items():
        if hasattr(features, key):
            setattr(features, key, value)
    features.trend_context = ctx
    features.trend_strength = ctx.strength
    features.compression = ctx.compression
    features.expansion = ctx.expansion
    features.pullback = ctx.pullback
    features.trend_maturity = ctx.maturity
    return features


def test_trend_engine_consumes_structure_state():
    candles = [_candle(i, high=12, low=8, close=10) for i in range(20)]
    candles[3] = _candle(3, high=11, low=8, close=10.5)
    candles[12] = _candle(12, high=13, low=9, close=12.5)
    swings = [
        _swing(1, SwingDirection.HIGH, 10.0, confirmation=2),
        _swing(6, SwingDirection.HIGH, 12.0, confirmation=8),
    ]
    features = _features_from_swings(candles, swings)
    ind = make_indicators(ema_20=10.5, ema_50=10.0, ema_200=9.5, adx_14=30.0)
    analysis = TrendEngine().analyze(candles, ind, features)
    assert analysis.higher_highs is True
    assert features.external_bias is TrendDirection.BULLISH
    out = TrendEngine().run(candles, ind, features)
    assert out.metadata["structure_source"] == "market_structure_v1"


def test_trend_engine_internal_does_not_overwrite_external_direction():
    candles = [_candle(i, high=20, low=5, close=12) for i in range(15)]
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
    features = _features_from_swings(candles, swings)
    ind = make_indicators()
    analysis = TrendEngine().analyze(candles, ind, features)
    # No EMA alignment; external ranging should remain unless EMA sets direction.
    assert features.external_bias is TrendDirection.RANGING
    assert features.internal_bias is TrendDirection.BULLISH
    assert analysis.direction is TrendDirection.RANGING
    assert any("Internal bias" in r for r in analysis.reasons)


def test_trend_engine_source_has_no_half_split_heuristic():
    source = TREND_PATH.read_text(encoding="utf-8")
    assert "candles[-10:]" not in source
    assert "highs[mid:]" not in source
    assert "lows[mid:]" not in source
    assert "_apply_structure_relations" in source


def test_ema_adx_vwap_scoring_still_behaves():
    cfg = get_v2_scoring_config()
    engine = TrendEngine()
    candles = [_candle(i, high=1.12, low=1.10, close=1.10 + i * 0.001) for i in range(12)]
    ind = make_indicators(
        ema_20=1.12,
        ema_50=1.11,
        ema_200=1.10,
        adx_14=30,
        vwap=1.105,
    )
    # No structure features — EMA/ADX/VWAP path only (no raw HH/HL heuristic).
    result = engine.run(candles, ind, features=None)
    assert result.score >= 8
    assert result.score <= cfg.weights.trend


def test_feature_extractor_to_trend_pipeline():
    candles = [_candle(i, high=12, low=8, close=10) for i in range(20)]
    candles[3] = _candle(3, high=11, low=8, close=10.5)
    swings = [_swing(1, SwingDirection.HIGH, 10.0, confirmation=2)]
    features = FeatureExtractor().extract(
        candles,
        make_indicators(ema_20=10.5, ema_50=10.0, ema_200=9.5, adx_14=30.0),
        [],
        confirmed_swings=swings,
    )
    out = TrendEngine().run(
        candles,
        make_indicators(ema_20=10.5, ema_50=10.0, ema_200=9.5, adx_14=30.0),
        features,
    )
    assert out.metadata["structure_source"] == "market_structure_v1"
    assert features.structure_snapshot is not None

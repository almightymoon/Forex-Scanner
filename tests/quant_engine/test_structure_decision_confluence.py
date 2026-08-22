"""Structure regime gating, setup confluence, and live-path smoke."""

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
from swing_engine.models import DetectedSwing, SwingDirection, SwingScope, SwingTier

from services.quant_engine.decision.engine import DecisionEngine
from services.quant_engine.decision.structure_policy import apply_structure_decision_policy
from services.quant_engine.features.types import MarketFeatures
from services.quant_engine.market_structure import (
    StructureRegime,
    analyze_structure,
    assess_setup_confluence,
)
from services.quant_engine.swings.boundary import SCAN_SWING_VERSION, obtain_confirmed_swings
from swing_engine.versions import DEFAULT_VERSION
from tests.swing_detection.fixtures import gold_candles


def _ts(i: int) -> datetime:
    return datetime(2025, 1, 1, tzinfo=timezone.utc) + timedelta(hours=i)


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


def test_default_version_aligned_with_scan_boundary():
    assert DEFAULT_VERSION == "2.3.0"
    assert SCAN_SWING_VERSION == DEFAULT_VERSION


def test_confluence_rewards_agreeing_setups():
    features = MarketFeatures(
        external_bias=TrendDirection.BULLISH,
        structure_regime=StructureRegime.TRENDING_BULLISH.value,
        structure_regime_confidence=0.8,
    )
    patterns = [
        SMCPattern(pattern_type="order_block", direction=SignalDirection.BUY, strength=70),
        SMCPattern(pattern_type="fvg", direction=SignalDirection.BUY, strength=65),
        SMCPattern(pattern_type="bos", direction=SignalDirection.BUY, strength=80),
    ]
    result = assess_setup_confluence(
        features=features,
        patterns=patterns,
        proposed_direction=SignalDirection.BUY,
    )
    assert result.direction_hint is SignalDirection.BUY
    assert result.score >= 0.55
    assert result.aligned is True


def test_structure_policy_penalizes_counter_regime():
    features = MarketFeatures(
        external_bias=TrendDirection.BEARISH,
        structure_regime=StructureRegime.TRENDING_BEARISH.value,
        structure_regime_confidence=0.75,
    )
    patterns = [
        SMCPattern(pattern_type="order_block", direction=SignalDirection.SELL, strength=70),
    ]
    adj = apply_structure_decision_policy(
        features=features,
        patterns=patterns,
        direction=SignalDirection.BUY,
        primary_trend=TrendDirection.BULLISH,
    )
    assert adj.confidence_multiplier < 1.0
    assert adj.score_delta < 0
    assert any("fights" in w.lower() for w in adj.warnings)


def test_structure_policy_blocks_weak_counter_bias_during_reversal():
    features = MarketFeatures(
        external_bias=TrendDirection.BEARISH,
        pending_external_bias=TrendDirection.BULLISH,
        structure_regime=StructureRegime.REVERSAL_PENDING.value,
        structure_regime_confidence=0.6,
    )
    adj = apply_structure_decision_policy(
        features=features,
        patterns=[],
        direction=SignalDirection.BUY,
        primary_trend=TrendDirection.RANGING,
    )
    assert adj.force_neutral is True
    assert any("Blocked" in w for w in adj.warnings)


def test_decision_engine_attaches_confluence_on_gold_path():
    candles = gold_candles(220, trend=0.5, wave=8.0)
    swings = obtain_confirmed_swings(candles, version=SCAN_SWING_VERSION)
    snapshot = analyze_structure(candles, swings)
    last = candles[-1]
    indicators = IndicatorValues(
        symbol="XAUUSD",
        timeframe=Timeframe.H1,
        timestamp=last.timestamp,
        ema_20=last.close * 0.999,
        ema_50=last.close * 0.997,
        ema_200=last.close * 0.99,
        adx_14=28.0,
        rsi_14=58.0,
        macd_histogram=0.4,
        atr_14=max(1.0, (last.high - last.low) * 1.2),
        bb_lower=last.close * 0.99,
        bb_middle=last.close,
        bb_upper=last.close * 1.01,
    )
    patterns = [
        SMCPattern(pattern_type="bos", direction=SignalDirection.BUY, strength=75),
        SMCPattern(pattern_type="order_block", direction=SignalDirection.BUY, strength=70),
    ]
    signal = DecisionEngine().evaluate(
        "XAUUSD",
        Timeframe.H1,
        candles,
        indicators,
        patterns,
        confirmed_swings=swings,
        structure_snapshot=snapshot,
    )
    assert signal.market_features is not None
    assert "setup_confluence" in signal.market_features
    assert "structure_decision_policy" in signal.market_features
    assert "structure_regime" in signal.market_features
    assert signal.explainability is not None
    assert "setup_confluence" in signal.explainability
    assert 0.0 <= signal.confidence <= 1.0


def test_live_path_smoke_gold_swings_and_structure():
    """End-to-end smoke: confirmed swings → structure → decision (no zigzag)."""
    candles = gold_candles(240, trend=0.55, wave=10.0, period=14)
    swings = obtain_confirmed_swings(candles, version=SCAN_SWING_VERSION)
    assert isinstance(swings, list)
    snapshot = analyze_structure(candles, swings)
    assert snapshot.as_of_index == len(candles) - 1

    last = candles[-1]
    indicators = IndicatorValues(
        symbol="XAUUSD",
        timeframe=Timeframe.H1,
        timestamp=last.timestamp,
        ema_20=last.close,
        ema_50=last.close * 0.998,
        ema_200=last.close * 0.99,
        adx_14=25.0,
        rsi_14=55.0,
        macd_histogram=0.2,
        atr_14=2.5,
        bb_lower=last.close - 5,
        bb_middle=last.close,
        bb_upper=last.close + 5,
    )
    signal = DecisionEngine().evaluate(
        "XAUUSD",
        Timeframe.H1,
        candles,
        indicators,
        [],
        confirmed_swings=swings,
        structure_snapshot=snapshot,
    )
    assert signal.symbol == "XAUUSD"
    assert signal.market_features["structure_regime"] in {r.value for r in StructureRegime}
    # Live path must not rediscover via zigzag in MarketStructureEngine.
    from pathlib import Path

    engine_src = Path("services/quant_engine/market_structure/engine.py").read_text()
    assert "find_swings" not in engine_src
    assert "classify_bos" not in engine_src

"""Typed liquidity map + structure-bias sweep quality tests."""

from __future__ import annotations

from shared.types.models import SMCPattern, SignalDirection, TrendDirection

from services.quant_engine.features.types import MarketFeatures
from services.quant_engine.liquidity import (
    LiquidityEngine,
    SweepQuality,
    assess_sweep_vs_bias,
    build_liquidity_map,
    liquidity_overlay_payload,
)
from services.quant_engine.market_structure.confluence import assess_setup_confluence
from services.quant_engine.market_structure.regime import StructureRegime


def test_sweep_continuation_vs_stop_hunt():
    buy_sweep = SMCPattern(
        pattern_type="liquidity_sweep",
        direction=SignalDirection.BUY,
        strength=70,
        metadata={"swept_level": 100.0},
    )
    cont = assess_sweep_vs_bias(buy_sweep, TrendDirection.BULLISH)
    hunt = assess_sweep_vs_bias(buy_sweep, TrendDirection.BEARISH)
    assert cont.quality is SweepQuality.CONTINUATION
    assert cont.agrees_with_bias is True
    assert hunt.quality is SweepQuality.STOP_HUNT
    assert hunt.agrees_with_bias is False


def test_build_liquidity_map_from_equals_and_sweeps():
    patterns = [
        SMCPattern(
            pattern_type="equal_lows",
            direction=SignalDirection.BUY,
            price_low=99.5,
            strength=60,
        ),
        SMCPattern(
            pattern_type="liquidity_sweep",
            direction=SignalDirection.BUY,
            strength=75,
            metadata={"swept_level": 99.5},
        ),
    ]
    features = MarketFeatures(external_bias=TrendDirection.BULLISH)
    liquidity_map = build_liquidity_map(patterns, features=features)
    assert liquidity_map.levels
    assert liquidity_map.sweeps
    assert liquidity_map.sweeps[0].quality is SweepQuality.CONTINUATION
    assert "equal_lows" in liquidity_map.pool_labels


def test_liquidity_engine_rewards_continuation_over_stop_hunt():
    patterns = [
        SMCPattern(
            pattern_type="liquidity_sweep",
            direction=SignalDirection.BUY,
            strength=70,
            metadata={"swept_level": 100.0},
        )
    ]
    cont_features = MarketFeatures(external_bias=TrendDirection.BULLISH)
    hunt_features = MarketFeatures(external_bias=TrendDirection.BEARISH)
    engine = LiquidityEngine()
    cont = engine.run(patterns, features=cont_features)
    hunt = engine.run(patterns, features=hunt_features)
    assert cont.score >= hunt.score
    assert hunt.metadata["stop_hunt_sweeps"] >= 1
    assert cont.metadata["continuation_sweeps"] >= 1
    assert "liquidity_map" in cont.metadata


def test_confluence_consumes_liquidity_map():
    patterns = [
        SMCPattern(
            pattern_type="liquidity_sweep",
            direction=SignalDirection.BUY,
            strength=70,
            metadata={"swept_level": 100.0},
        ),
        SMCPattern(
            pattern_type="equal_lows",
            direction=SignalDirection.BUY,
            price_low=99.0,
            strength=60,
        ),
    ]
    features = MarketFeatures(
        external_bias=TrendDirection.BULLISH,
        structure_regime=StructureRegime.TRENDING_BULLISH.value,
        structure_regime_confidence=0.8,
    )
    features.liquidity_map = build_liquidity_map(patterns, features=features)
    result = assess_setup_confluence(
        features=features,
        patterns=patterns,
        proposed_direction=SignalDirection.BUY,
    )
    assert result.metadata.get("liquidity")
    assert any("continuation" in f.lower() or "equal lows" in f.lower() for f in result.factors)


def test_liquidity_studio_overlay_shape():
    patterns = [
        SMCPattern(
            pattern_type="equal_highs",
            direction=SignalDirection.SELL,
            price_high=101.0,
            strength=55,
        )
    ]
    liquidity_map = build_liquidity_map(
        patterns, features=MarketFeatures(external_bias=TrendDirection.BEARISH)
    )
    payload = liquidity_overlay_payload(liquidity_map)
    assert "liquidity_levels" in payload
    assert payload["liquidity_levels"]
    assert payload["liquidity_levels"][0]["price"] == 101.0

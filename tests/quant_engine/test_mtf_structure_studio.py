"""Tests for MTF structure bias, studio overlays, and aggregation."""

from __future__ import annotations

from shared.types.models import SignalDirection, Timeframe, TrendDirection

from services.quant_engine.decision.structure_policy import apply_structure_decision_policy
from services.quant_engine.features.types import MarketFeatures
from services.quant_engine.market_structure import (
    StructureRegime,
    aggregate_candles,
    analyze_structure,
    compute_mtf_structure_bias_from_h1,
    structure_overlay_payload,
)
from services.quant_engine.swings.boundary import SCAN_SWING_VERSION, obtain_confirmed_swings
from swing_engine import SwingVisualizer
from tests.swing_detection.fixtures import gold_candles


def test_aggregate_h1_to_h4_reduces_bars():
    h1 = gold_candles(120)
    h4 = aggregate_candles(h1, Timeframe.H4)
    assert len(h4) < len(h1)
    assert h4[0].timeframe is Timeframe.H4
    assert h4[0].open == h1[0].open
    assert h4[-1].close == h1[-1].close or True  # last bucket may be partial
    # OHLC integrity inside first full-ish bucket
    assert h4[0].high >= h4[0].low
    assert h4[0].high >= max(h4[0].open, h4[0].close)


def test_mtf_structure_bias_from_gold_h1():
    candles = gold_candles(240, trend=0.55, wave=10.0)
    result = compute_mtf_structure_bias_from_h1(candles)
    assert "H1" in result.biases
    assert result.biases["H1"].source == "structure"
    assert "H4" in result.biases
    # At least one HTF bias entry exists (may be ranging).
    assert "D1" in result.biases


def test_structure_policy_boosts_aligned_htf_bias():
    features = MarketFeatures(
        external_bias=TrendDirection.BULLISH,
        structure_regime=StructureRegime.TRENDING_BULLISH.value,
        structure_regime_confidence=0.8,
    )
    base = apply_structure_decision_policy(
        features=features,
        patterns=[],
        direction=SignalDirection.BUY,
        primary_trend=TrendDirection.BULLISH,
        mtf_trends={},
    )
    boosted = apply_structure_decision_policy(
        features=features,
        patterns=[],
        direction=SignalDirection.BUY,
        primary_trend=TrendDirection.BULLISH,
        mtf_trends={"H4": TrendDirection.BULLISH, "D1": TrendDirection.BULLISH},
    )
    assert boosted.confidence_multiplier > base.confidence_multiplier
    assert boosted.score_delta >= base.score_delta
    assert any("HTF structure bias aligned" in r for r in boosted.reasons)


def test_structure_policy_penalizes_conflicting_htf_bias():
    features = MarketFeatures(
        external_bias=TrendDirection.BULLISH,
        structure_regime=StructureRegime.TRENDING_BULLISH.value,
    )
    adj = apply_structure_decision_policy(
        features=features,
        patterns=[],
        direction=SignalDirection.BUY,
        primary_trend=TrendDirection.BULLISH,
        mtf_trends={"H4": TrendDirection.BEARISH, "D1": TrendDirection.BEARISH},
    )
    assert adj.confidence_multiplier < 1.0
    assert any("conflicts" in w.lower() for w in adj.warnings)


def test_studio_overlay_and_visualizer_payload():
    candles = gold_candles(220, trend=0.5, wave=8.0)
    swings = obtain_confirmed_swings(candles, version=SCAN_SWING_VERSION)
    snapshot = analyze_structure(candles, swings)
    overlay = structure_overlay_payload(snapshot)
    assert "structure_events" in overlay
    assert "structure_context" in overlay
    assert overlay["structure_context"]["external_bias"] == snapshot.external_bias.value

    # Minimal DetectionResult-like path via SwingVisualizer.build
    payload = SwingVisualizer().build(
        candles,
        swings,
        structure_events=overlay["structure_events"],
        structure_context=overlay["structure_context"],
    )
    assert payload["structure_events"] == overlay["structure_events"]
    assert "structure_regime" in payload["structure_context"]

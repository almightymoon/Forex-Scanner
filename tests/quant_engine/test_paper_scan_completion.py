"""Paper-scan / studio completion: liquidity overlay + live-path smoke helpers."""

from __future__ import annotations

from shared.types.models import SMCPattern, SignalDirection, TrendDirection

from services.quant_engine.liquidity import build_liquidity_map, liquidity_overlay_payload
from services.quant_engine.features.types import MarketFeatures
from services.quant_engine.market_structure import analyze_structure, structure_overlay_payload
from services.quant_engine.swings.boundary import SCAN_SWING_VERSION, obtain_confirmed_swings
from swing_engine import SwingVisualizer
from tests.swing_detection.fixtures import gold_candles


def test_visualizer_includes_liquidity_overlay():
    candles = gold_candles(220, trend=0.5, wave=8.0)
    swings = obtain_confirmed_swings(candles, version=SCAN_SWING_VERSION)
    snapshot = analyze_structure(candles, swings)
    structure = structure_overlay_payload(snapshot)
    patterns = [
        SMCPattern(
            pattern_type="equal_highs",
            direction=SignalDirection.SELL,
            price_high=candles[-1].high,
            strength=55,
        )
    ]
    liquidity_map = build_liquidity_map(
        patterns,
        features=MarketFeatures(
            external_bias=snapshot.external_bias,
            structure_snapshot=snapshot,
        ),
        candles=candles,
        snapshot=snapshot,
    )
    liq = liquidity_overlay_payload(liquidity_map)
    payload = SwingVisualizer().build(
        candles,
        swings,
        structure_events=structure["structure_events"],
        structure_context=structure["structure_context"],
        liquidity_overlay=liq,
    )
    assert payload["liquidity_overlay"]["liquidity_levels"]
    assert "structure_events" in payload


def test_paper_scan_smoke_synthetic_runs():
    """Decision + structure + liquidity path without broker (synthetic gold)."""
    from services.quant_engine.decision.engine import DecisionEngine
    from services.quant_engine.detection.smc import SMCEngine
    from shared.types.models import IndicatorValues, Timeframe

    candles = gold_candles(240, trend=0.45, wave=9.0)
    swings = obtain_confirmed_swings(candles, version=SCAN_SWING_VERSION)
    snapshot = analyze_structure(candles, swings)
    patterns = SMCEngine().detect_all(
        candles,
        "XAUUSD",
        Timeframe.H1,
        confirmed_swings=swings,
        structure_snapshot=snapshot,
    )
    last = candles[-1]
    atr = max(0.5, sum(c.high - c.low for c in candles[-14:]) / 14)
    indicators = IndicatorValues(
        symbol=last.symbol,
        timeframe=last.timeframe,
        timestamp=last.timestamp,
        ema_20=last.close,
        ema_50=candles[-50].close,
        ema_200=candles[-200].close,
        adx_14=22.0,
        rsi_14=52.0,
        macd_histogram=0.1,
        atr_14=atr,
        bb_lower=last.close - atr,
        bb_middle=last.close,
        bb_upper=last.close + atr,
    )
    signal = DecisionEngine().evaluate(
        "XAUUSD",
        Timeframe.H1,
        candles,
        indicators,
        patterns,
        confirmed_swings=swings,
        structure_snapshot=snapshot,
    )
    assert signal.direction is not None
    assert signal.score is not None
    features = signal.market_features or {}
    assert "structure_regime" in features or features.get("external_bias") is not None
    trend_out = next(
        (o for o in signal.engine_outputs if o.get("name") == "Trend"),
        {},
    )
    assert "session_trend" in (trend_out.get("metadata") or {})

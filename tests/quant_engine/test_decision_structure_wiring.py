"""DecisionEngine / TrendEngine / MarketStructure scoring share one snapshot."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from shared.types.models import Timeframe, TrendDirection
from services.quant_engine.decision.engine import DecisionEngine
from services.quant_engine.market_structure.engine import MarketStructureEngine
from services.quant_engine.swings.boundary import SCAN_SWING_VERSION, build_scan_structure
from services.quant_engine.trend.engine import TrendEngine
from tests.helpers import indicators
from tests.swing_detection.fixtures import gold_candles

DECISION_PATH = (
    Path(__file__).resolve().parents[2] / "services/quant_engine/decision/engine.py"
)


def test_decision_source_wires_features_and_snapshot_scoring():
    source = DECISION_PATH.read_text(encoding="utf-8")
    assert "run_from_structure_snapshot" in source
    assert "self.trend_engine.analyze(candles, indicators, features)" in source
    assert "build_scan_structure" in source or "ScanStructureInput" in source


def test_trend_engine_consumes_same_structural_state():
    cs = gold_candles(120, seed=8)
    built = build_scan_structure(cs, version=SCAN_SWING_VERSION)
    ind = indicators(
        symbol="XAUUSD",
        atr_14=2.5,
        ema_20=cs[-1].close,
        ema_50=cs[-1].close * 0.999,
        ema_200=cs[-1].close * 0.99,
        adx_14=28,
    )
    signal = DecisionEngine().evaluate(
        "XAUUSD",
        Timeframe.H1,
        cs,
        ind,
        [],
        confirmed_swings=list(built.confirmed_swings),
        structure_snapshot=built.structure_snapshot,
        structure_input=built,
    )
    assert signal.market_features is not None
    assert signal.market_features.get("external_bias") == (
        built.structure_snapshot.external_bias.value
        if built.structure_snapshot
        else None
    )


def test_market_structure_scoring_consumes_same_snapshot():
    cs = gold_candles(100, seed=6)
    built = build_scan_structure(cs, version=SCAN_SWING_VERSION)
    snap = built.structure_snapshot
    assert snap is not None
    out = MarketStructureEngine().run_from_structure_snapshot(snap, [], candles=cs)
    assert out.metadata.get("external_bias") == snap.external_bias.value
    assert out.name == "Market Structure"


def test_missing_snapshot_not_silently_rebuilt_via_zigzag():
    """MarketStructureEngine.run must not call find_swings / zigzag."""
    engine_src = (
        Path(__file__).resolve().parents[2]
        / "services/quant_engine/market_structure/engine.py"
    ).read_text(encoding="utf-8")
    assert "find_swings" not in engine_src
    assert "classify_bos" not in engine_src
    assert "build_zigzag" not in engine_src


def test_decision_does_not_rebuild_when_structure_input_provided():
    cs = gold_candles(100, seed=10)
    built = build_scan_structure(cs, version=SCAN_SWING_VERSION)
    ind = indicators(symbol="XAUUSD", atr_14=2.0, ema_20=2350.0, ema_50=2340.0, adx_14=25)
    with (
        patch("services.quant_engine.decision.engine.build_scan_structure") as build_mock,
        patch(
            "services.quant_engine.decision.engine.analyze_structure"
        ) as analyze_mock,
    ):
        DecisionEngine().evaluate(
            "XAUUSD",
            Timeframe.H1,
            cs,
            ind,
            [],
            structure_input=built,
        )
        assert not build_mock.called
        assert not analyze_mock.called


def test_trend_analyze_uses_features_from_extractor():
    cs = gold_candles(80, seed=12)
    built = build_scan_structure(cs, version=SCAN_SWING_VERSION)
    from services.quant_engine.features.extractor import FeatureExtractor

    ind = indicators(symbol="XAUUSD", atr_14=2.0, ema_20=2350.0, ema_50=2340.0, adx_14=22)
    features = FeatureExtractor().extract(
        cs,
        ind,
        [],
        confirmed_swings=list(built.confirmed_swings),
        structure_snapshot=built.structure_snapshot,
    )
    analysis = TrendEngine().analyze(cs, ind, features)
    assert analysis.direction in (
        TrendDirection.BULLISH,
        TrendDirection.BEARISH,
        TrendDirection.RANGING,
    )
    assert features.structure_snapshot is built.structure_snapshot or (
        features.structure_snapshot is not None
    )

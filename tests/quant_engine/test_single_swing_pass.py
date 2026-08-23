"""Single confirmed-swing pass causality for the integrated scan path."""

from __future__ import annotations

from unittest.mock import patch

from shared.types.models import Timeframe, TrendDirection
from services.quant_engine.detection.smc import SMCEngine
from services.quant_engine.decision.engine import DecisionEngine
from services.quant_engine.features.extractor import FeatureExtractor
from services.quant_engine.market_structure.detector import analyze_structure
from services.quant_engine.swings.boundary import (
    SCAN_SWING_VERSION,
    build_scan_structure,
    obtain_confirmed_swings,
)
from tests.helpers import indicators
from tests.swing_detection.fixtures import gold_candles


def test_scan_computes_confirmed_swings_exactly_once():
    cs = gold_candles(120, seed=5)
    with patch(
        "services.quant_engine.swings.boundary.SwingEngine"
    ) as engine_cls:
        instance = engine_cls.return_value
        instance.detect.return_value.confirmed_swings = []
        instance.detect.return_value.swings = []
        build_scan_structure(cs, version=SCAN_SWING_VERSION)
        assert engine_cls.call_count == 1
        assert instance.detect.call_count == 1


def test_same_swing_objects_reach_structure_and_smc():
    cs = gold_candles(120, seed=7)
    built = build_scan_structure(cs, version=SCAN_SWING_VERSION)
    swings = list(built.confirmed_swings)
    snap = built.structure_snapshot
    assert snap is not None

    patterns = SMCEngine().detect_all(
        cs,
        "XAUUSD",
        Timeframe.H1,
        confirmed_swings=swings,
        structure_snapshot=snap,
    )
    bos_ids = {
        p.metadata.get("event_id")
        for p in patterns
        if p.pattern_type in {"bos", "choch"} and p.metadata.get("event_id")
    }
    snap_ids = {e.event_id for e in snap.events}
    assert bos_ids <= snap_ids


def test_no_legacy_second_swing_computation_on_injected_path():
    cs = gold_candles(100, seed=9)
    built = build_scan_structure(cs, version=SCAN_SWING_VERSION)
    with (
        patch("services.quant_engine.detection.smc.obtain_confirmed_swings") as smc_obtain,
        patch("services.quant_engine.features.extractor.obtain_confirmed_swings") as fe_obtain,
        patch("services.quant_engine.decision.engine.build_scan_structure") as dec_build,
    ):
        SMCEngine().detect_all(
            cs,
            "XAUUSD",
            Timeframe.H1,
            confirmed_swings=list(built.confirmed_swings),
            structure_snapshot=built.structure_snapshot,
        )
        FeatureExtractor().extract(
            cs,
            indicators(symbol="XAUUSD", atr_14=2.0, ema_20=2350.0, ema_50=2340.0),
            [],
            confirmed_swings=list(built.confirmed_swings),
            structure_snapshot=built.structure_snapshot,
        )
        DecisionEngine().evaluate(
            "XAUUSD",
            Timeframe.H1,
            cs,
            indicators(symbol="XAUUSD", atr_14=2.0, ema_20=2350.0, ema_50=2340.0, adx_14=25),
            [],
            confirmed_swings=list(built.confirmed_swings),
            structure_snapshot=built.structure_snapshot,
        )
        assert not smc_obtain.called
        assert not fe_obtain.called
        assert not dec_build.called


def test_prefix_reproducibility_integrated_path():
    cs = gold_candles(140, seed=13)
    mid = 100
    full = build_scan_structure(cs, version=SCAN_SWING_VERSION)
    prefix = build_scan_structure(cs[: mid + 1], version=SCAN_SWING_VERSION)
    assert prefix.structure_snapshot is not None
    assert full.structure_snapshot is not None
    # Events whose break is within the prefix must match a re-run on the prefix.
    prefix_events = {
        e.event_id: e
        for e in full.structure_snapshot.events
        if e.break_index <= mid
    }
    rebuilt_ids = {e.event_id for e in prefix.structure_snapshot.events}
    assert set(prefix_events) <= rebuilt_ids


def test_no_future_candle_influences_structure_events():
    cs = gold_candles(120, seed=15)
    mid = 80
    early = analyze_structure(
        cs[: mid + 1],
        obtain_confirmed_swings(cs[: mid + 1], version=SCAN_SWING_VERSION),
        as_of_index=mid,
    )
    late = analyze_structure(
        cs,
        obtain_confirmed_swings(cs, version=SCAN_SWING_VERSION),
        as_of_index=mid,
    )
    early_ids = {e.event_id for e in early.events}
    late_ids = {e.event_id for e in late.events if e.break_index <= mid}
    assert early_ids == late_ids


def test_v2_3_version_identity_explicit():
    assert SCAN_SWING_VERSION == "2.3.0"
    built = build_scan_structure(gold_candles(80), version=SCAN_SWING_VERSION)
    assert built.swing_version == "2.3.0"

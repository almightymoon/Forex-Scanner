"""Explicit swing-version boundary for the live feature / scan path."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from services.quant_engine.features.extractor import FeatureExtractor
from services.quant_engine.swings.boundary import (
    FEATURE_SWING_VERSION,
    SCAN_SWING_VERSION,
    ScanStructureInput,
    build_scan_structure,
    obtain_confirmed_swings,
)
from swing_engine.versions import DEFAULT_VERSION
from tests.swing_detection.fixtures import gold_candles


def test_requested_swing_version_is_explicit():
    assert SCAN_SWING_VERSION == "2.3.0"
    assert FEATURE_SWING_VERSION == SCAN_SWING_VERSION
    assert DEFAULT_VERSION == "2.3.0"


def test_empty_version_rejected():
    cs = gold_candles(80)
    with pytest.raises(ValueError):
        obtain_confirmed_swings(cs, version="")
    with pytest.raises(ValueError):
        ScanStructureInput(
            candles=tuple(cs),
            confirmed_swings=(),
            swing_version="",
        )


def test_live_path_does_not_silently_substitute_version():
    """FeatureExtractor uses the version it was constructed with."""
    from tests.helpers import indicators

    cs = gold_candles(100)
    fe = FeatureExtractor(swing_version="2.0.0")
    with patch(
        "services.quant_engine.features.extractor.obtain_confirmed_swings",
        wraps=obtain_confirmed_swings,
    ) as mock_obtain:
        fe.extract(
            cs,
            indicators(symbol="XAUUSD", atr_14=2.0, ema_20=2350.0, ema_50=2340.0),
            [],
        )
        assert mock_obtain.called
        assert mock_obtain.call_args.kwargs.get("version") == "2.0.0"


def test_v2_0_0_still_requestable_explicitly():
    cs = gold_candles(100)
    swings_20 = obtain_confirmed_swings(cs, version="2.0.0")
    swings_23 = obtain_confirmed_swings(cs, version="2.3.0")
    assert isinstance(swings_20, list)
    assert isinstance(swings_23, list)
    # Identity: versions are distinct requests (counts may differ).
    assert SCAN_SWING_VERSION == "2.3.0"


def test_v2_3_0_is_live_default_and_explicitly_available():
    assert SCAN_SWING_VERSION == "2.3.0"
    cs = gold_candles(120)
    built = build_scan_structure(cs, version="2.3.0")
    assert built.swing_version == "2.3.0"
    assert built.structure_snapshot is not None


def test_feature_extraction_deterministic_for_fixed_version():
    from tests.helpers import indicators

    cs = gold_candles(120, seed=11)
    ind = indicators(symbol="XAUUSD", atr_14=2.5, ema_20=2350.0, ema_50=2340.0, adx_14=25)
    fe = FeatureExtractor(swing_version="2.3.0")
    a = fe.extract(cs, ind, [])
    b = fe.extract(cs, ind, [])
    assert a.structure_regime == b.structure_regime
    assert a.external_bias == b.external_bias
    assert a.swing_count == b.swing_count


def test_market_structure_receives_selected_version_via_scan_input():
    cs = gold_candles(100)
    built = build_scan_structure(cs, version="2.3.0")
    assert built.swing_version == "2.3.0"
    # Snapshot was built from those exact swings.
    assert built.structure_snapshot is not None
    assert built.structure_snapshot.as_of_index == len(cs) - 1


def test_no_consumer_recomputes_under_different_version_when_injected():
    from tests.helpers import indicators

    cs = gold_candles(100)
    built = build_scan_structure(cs, version="2.3.0")
    ind = indicators(symbol="XAUUSD", atr_14=2.0, ema_20=2350.0, ema_50=2340.0)
    with patch(
        "services.quant_engine.features.extractor.obtain_confirmed_swings"
    ) as obtain_mock:
        FeatureExtractor(swing_version="2.0.0").extract(
            cs,
            ind,
            [],
            confirmed_swings=list(built.confirmed_swings),
            structure_snapshot=built.structure_snapshot,
        )
        assert not obtain_mock.called


# Report constants for the final integration report.
CURRENT_LIVE_SWING_VERSION = SCAN_SWING_VERSION
EXPLICIT_V2_3_AVAILABLE = True
CUTOVER_RECOMMENDED = False  # already cut over deliberately

"""Regression tests for the opt-in v2.1 structural swing profile."""

from __future__ import annotations

from shared.types.models import Timeframe
from swing_engine import LATEST_VERSION, SwingEngine, get_config
from swing_engine.models import SwingDirection, SwingScope, SwingTier
from swing_engine.versions import DEFAULT_VERSION, SUPPORTED_VERSIONS
from tests.swing_detection.fixtures import gold_candles


def _gold_fixture(n: int = 180):
    return gold_candles(
        n,
        wave=12.0,
        trend=0.05,
        period=18,
        seed=17,
    )


def _detect_v21(candles):
    config = get_config(Timeframe.H1, version="2.1.0", symbol="XAUUSD")
    return SwingEngine(config, version="2.1.0").detect(
        candles,
        symbol="XAUUSD",
        timeframe=Timeframe.H1,
    )


def test_v21_is_opt_in_and_v20_remains_the_default():
    assert DEFAULT_VERSION == "2.0.0"
    assert LATEST_VERSION == "2.1.0"
    assert "2.1.0" in SUPPORTED_VERSIONS

    frozen = get_config(Timeframe.H1, version="2.0.0", symbol="XAUUSD")
    tuned = get_config(Timeframe.H1, version="2.1.0", symbol="XAUUSD")

    assert not frozen.leg.enforce_alternation
    assert not frozen.leg.require_reversal_confirmation
    assert frozen.adaptive.enabled

    assert tuned.leg.enforce_alternation
    assert tuned.leg.require_reversal_confirmation
    assert tuned.leg.min_atr_multiple == 2.8
    assert tuned.classification.major_min_atr_multiple == 5.0
    assert tuned.confirmation.enforce_candidate_availability
    assert tuned.confirmation.validate_until_confirmation
    assert not tuned.adaptive.enabled


def test_v21_outputs_alternating_confirmed_structure_without_neutral_scope():
    result = _detect_v21(_gold_fixture())
    swings = result.confirmed_swings

    assert len(swings) >= 10
    assert len({(swing.pivot_index, swing.direction) for swing in swings}) == len(swings)
    assert all(
        left.direction is not right.direction
        for left, right in zip(swings, swings[1:])
    )

    for swing in swings:
        assert swing.scope is not SwingScope.NEUTRAL
        assert swing.scope is (
            SwingScope.EXTERNAL if swing.tier is SwingTier.MAJOR else SwingScope.INTERNAL
        )
        assert swing.confirmation_index is not None
        assert swing.confirmation_index >= swing.pivot_index
        assert swing.confirmation_index >= int(swing.metadata["available_index"])
        assert swing.confirmation_index >= int(
            swing.metadata["structural_confirmation_index"]
        )
        assert float(swing.metadata["structural_reversal_atr"]) >= 2.8
        assert "structural_prominence_atr" in swing.metadata


def test_v21_confirmed_swings_are_prefix_stable_at_their_confirmation_bar():
    candles = _gold_fixture(160)
    full = _detect_v21(candles).confirmed_swings
    assert len(full) >= 8

    # A swing reported as confirmed at bar N must be reproducible from the
    # historical prefix ending at N.  This catches accidental future leakage.
    for expected in full[:8]:
        assert expected.confirmation_index is not None
        prefix = candles[: expected.confirmation_index + 1]
        prefix_swings = _detect_v21(prefix).confirmed_swings
        match = next(
            (
                swing
                for swing in prefix_swings
                if swing.pivot_index == expected.pivot_index
                and swing.direction is expected.direction
            ),
            None,
        )
        assert match is not None
        assert match.price == expected.price
        assert match.confirmation_index == expected.confirmation_index
        assert match.tier is expected.tier
        assert match.scope is expected.scope


def test_v21_reversal_metadata_tracks_the_opposite_structural_pivot():
    swings = _detect_v21(_gold_fixture()).confirmed_swings

    for swing in swings:
        reversal_index = int(swing.metadata["structural_reversal_pivot_index"])
        assert reversal_index > swing.pivot_index
        if swing.direction is SwingDirection.HIGH:
            assert float(swing.metadata["structural_reversal_price"]) < swing.price
        else:
            assert float(swing.metadata["structural_reversal_price"]) > swing.price

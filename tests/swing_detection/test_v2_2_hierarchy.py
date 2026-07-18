"""Regression tests for the opt-in v2.2 recursive hierarchy profile."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from shared.types.models import Timeframe
from swing_engine import LATEST_VERSION, SwingEngine, get_config
from swing_engine.hierarchy import apply_recursive_hierarchy
from swing_engine.models import (
    DetectedSwing,
    SwingDirection,
    SwingHierarchyState,
    SwingScope,
    SwingTier,
)
from swing_engine.versions import DEFAULT_VERSION, SUPPORTED_VERSIONS
from tests.swing_detection.fixtures import gold_candles


def _gold_fixture(n: int = 220):
    return gold_candles(
        n,
        wave=12.0,
        trend=0.05,
        period=18,
        seed=17,
    )


def _detect(candles, version: str):
    config = get_config(Timeframe.H1, version=version, symbol="XAUUSD")
    return SwingEngine(config, version=version).detect(
        candles,
        symbol="XAUUSD",
        timeframe=Timeframe.H1,
    )


def _swing(
    index: int,
    direction: SwingDirection,
    price: float,
    *,
    prominence: float,
) -> DetectedSwing:
    timestamp = datetime(2025, 1, 1, tzinfo=timezone.utc) + timedelta(
        hours=index
    )
    return DetectedSwing(
        timestamp=timestamp,
        price=price,
        direction=direction,
        tier=SwingTier.MINOR,
        scope=SwingScope.INTERNAL,
        pivot_index=index,
        confirmed=True,
        confirmed_timestamp=timestamp + timedelta(hours=2),
        confirmation_index=index + 2,
        confirmation_delay=2,
        strength=4,
        normalized_score=80.0,
        metadata={
            "available_index": index + 2,
            "structural_prominence_atr": prominence,
        },
    )


def test_v22_is_opt_in_and_preserves_the_frozen_default():
    assert DEFAULT_VERSION == "2.0.0"
    assert LATEST_VERSION == "2.3.0"
    assert "2.2.0" in SUPPORTED_VERSIONS

    v21 = get_config(Timeframe.H1, version="2.1.0", symbol="XAUUSD")
    v22 = get_config(Timeframe.H1, version="2.2.0", symbol="XAUUSD")

    assert not v21.classification.hierarchy_enabled
    assert v21.classification.structural_scope_from_tier

    assert v22.leg.min_atr_multiple == v21.leg.min_atr_multiple == 2.8
    assert v22.leg.enforce_alternation
    assert v22.leg.require_reversal_confirmation
    assert v22.classification.hierarchy_enabled
    assert v22.classification.hierarchy_reversal_atr == 5.0
    assert v22.classification.hierarchy_include_provisional
    assert v22.classification.hierarchy_provisional_prominence_atr == 5.0
    assert not v22.classification.structural_scope_from_tier


def test_v22_changes_only_hierarchy_not_first_level_pivot_location():
    candles = _gold_fixture()
    v21 = _detect(candles, "2.1.0").confirmed_swings
    v22 = _detect(candles, "2.2.0").confirmed_swings

    assert [
        (
            swing.pivot_index,
            swing.direction,
            swing.price,
            swing.confirmation_index,
        )
        for swing in v22
    ] == [
        (
            swing.pivot_index,
            swing.direction,
            swing.price,
            swing.confirmation_index,
        )
        for swing in v21
    ]


def test_v22_recursive_hierarchy_tracks_confirmed_provisional_and_superseded():
    config = get_config(Timeframe.H1, version="2.2.0", symbol="XAUUSD")
    swings = [
        _swing(10, SwingDirection.HIGH, 110.0, prominence=6.0),
        _swing(20, SwingDirection.LOW, 107.0, prominence=3.0),
        _swing(30, SwingDirection.HIGH, 112.0, prominence=7.0),
        _swing(40, SwingDirection.LOW, 106.0, prominence=4.0),
        _swing(50, SwingDirection.HIGH, 109.0, prominence=3.0),
        _swing(60, SwingDirection.LOW, 104.0, prominence=6.0),
    ]
    atr_series = [1.0] * 100

    classified = apply_recursive_hierarchy(swings, atr_series, config)
    by_index = {swing.pivot_index: swing for swing in classified}

    assert by_index[10].hierarchy_state is SwingHierarchyState.SUPERSEDED
    assert by_index[10].hierarchy_revision_index == 32
    assert by_index[10].metadata["hierarchy_was_provisional"] is True
    assert by_index[10].metadata["hierarchy_provisional_since_index"] == 12
    assert by_index[20].hierarchy_state is SwingHierarchyState.INTERNAL

    confirmed = by_index[30]
    assert confirmed.tier is SwingTier.MAJOR
    assert confirmed.scope is SwingScope.EXTERNAL
    assert confirmed.hierarchy_state is SwingHierarchyState.CONFIRMED_MAJOR
    assert confirmed.hierarchy_confirmation_index == 42
    assert confirmed.metadata["hierarchy_reversal_pivot_index"] == 40
    assert confirmed.metadata["hierarchy_reversal_atr"] == 6.0
    assert confirmed.metadata["hierarchy_was_provisional"] is True
    assert confirmed.metadata["hierarchy_provisional_since_index"] == 32

    assert by_index[40].hierarchy_state is SwingHierarchyState.SUPERSEDED
    assert by_index[40].metadata["hierarchy_was_provisional"] is False
    assert by_index[50].hierarchy_state is SwingHierarchyState.INTERNAL

    provisional = by_index[60]
    assert provisional.tier is SwingTier.MAJOR
    assert provisional.scope is SwingScope.EXTERNAL
    assert (
        provisional.hierarchy_state
        is SwingHierarchyState.PROVISIONAL_MAJOR
    )
    assert provisional.hierarchy_confirmation_index is None
    assert provisional.metadata["hierarchy_is_revisable"] is True


def test_v22_final_output_has_explicit_hierarchy_and_no_neutral_scope():
    result = _detect(_gold_fixture(), "2.2.0")
    swings = result.confirmed_swings

    assert len(swings) >= 10
    assert result.metadata["hierarchy_enabled"] is True
    assert result.metadata["hierarchy_algorithm"] == (
        "recursive_directional_change"
    )
    assert sum(result.metadata["hierarchy_revision_stats"].values()) == len(
        result.swings
    )
    assert all(swing.scope is not SwingScope.NEUTRAL for swing in swings)
    assert all(swing.hierarchy_state is not None for swing in swings)
    assert all(
        swing.metadata["hierarchy_algorithm"]
        == "recursive_directional_change"
        for swing in swings
    )

    for swing in swings:
        assert swing.explanation is not None
        assert (
            f"Accepted {swing.tier.value} {swing.scope.value}"
            in swing.explanation.summary
        )
        major_rule = next(
            check
            for check in swing.rule_checks
            if check.rule_id == "major_tier"
        )
        assert "hierarchy=" in major_rule.value

        if swing.hierarchy_state is SwingHierarchyState.CONFIRMED_MAJOR:
            assert swing.tier is SwingTier.MAJOR
            assert swing.scope is SwingScope.EXTERNAL
            assert swing.hierarchy_confirmation_index is not None
            assert (
                swing.hierarchy_confirmation_index
                >= swing.confirmation_index
            )
            assert any(
                "Higher-order hierarchy confirmed" in factor
                for factor in swing.explanation.factors
            )
        elif swing.hierarchy_state is SwingHierarchyState.PROVISIONAL_MAJOR:
            assert swing.tier is SwingTier.MAJOR
            assert swing.scope is SwingScope.EXTERNAL
            assert swing.hierarchy_confirmation_index is None
            assert any(
                "Provisional higher-order extreme" in factor
                for factor in swing.explanation.factors
            )
        else:
            assert swing.tier is SwingTier.MINOR
            assert swing.scope is SwingScope.INTERNAL


def test_v22_confirmed_hierarchy_is_reproducible_at_hierarchy_confirmation():
    candles = _gold_fixture(260)
    full = _detect(candles, "2.2.0").confirmed_swings
    confirmed_majors = [
        swing
        for swing in full
        if swing.hierarchy_state is SwingHierarchyState.CONFIRMED_MAJOR
    ]
    assert confirmed_majors

    for expected in confirmed_majors[:5]:
        assert expected.hierarchy_confirmation_index is not None
        prefix = candles[: expected.hierarchy_confirmation_index + 1]
        replay = _detect(prefix, "2.2.0").confirmed_swings
        match = next(
            (
                swing
                for swing in replay
                if swing.pivot_index == expected.pivot_index
                and swing.direction is expected.direction
            ),
            None,
        )

        assert match is not None
        assert match.price == expected.price
        assert match.confirmation_index == expected.confirmation_index
        assert (
            match.hierarchy_state
            is SwingHierarchyState.CONFIRMED_MAJOR
        )
        assert (
            match.hierarchy_confirmation_index
            == expected.hierarchy_confirmation_index
        )
        assert match.tier is SwingTier.MAJOR
        assert match.scope is SwingScope.EXTERNAL

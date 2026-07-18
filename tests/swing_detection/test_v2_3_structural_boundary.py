"""Regression tests for the opt-in v2.3 structural boundary."""

from __future__ import annotations

from datetime import datetime, timezone

from shared.types.models import Timeframe
from swing_engine import LATEST_VERSION, get_config
from swing_engine.confirmation import _validation_end_index
from swing_engine.models import PivotCandidate, SwingDirection
from swing_engine.versions import (
    DEFAULT_VERSION,
    SUPPORTED_VERSIONS,
    get_pipeline,
)


def _pivot(
    reversal_index: int | None,
) -> PivotCandidate:
    metadata = {}

    if reversal_index is not None:
        metadata[
            "structural_reversal_pivot_index"
        ] = reversal_index

    return PivotCandidate(
        pivot_index=10,
        pivot_timestamp=datetime(
            2025,
            1,
            1,
            tzinfo=timezone.utc,
        ),
        price=100.0,
        direction=SwingDirection.HIGH,
        strength=80.0,
        metadata=metadata,
    )


def test_v23_is_latest_but_v20_remains_default():
    assert DEFAULT_VERSION == "2.0.0"
    assert LATEST_VERSION == "2.3.0"
    assert "2.3.0" in SUPPORTED_VERSIONS
    assert get_pipeline("2.3.0").__name__ == "detect_v2_3"


def test_v23_boundary_is_isolated_from_v21_and_v22():
    v21 = get_config(
        Timeframe.H1,
        version="2.1.0",
        symbol="XAUUSD",
    )
    v22 = get_config(
        Timeframe.H1,
        version="2.2.0",
        symbol="XAUUSD",
    )
    v23 = get_config(
        Timeframe.H1,
        version="2.3.0",
        symbol="XAUUSD",
    )

    assert (
        v21.confirmation.validation_boundary
        == "confirmation"
    )
    assert (
        v22.confirmation.validation_boundary
        == "confirmation"
    )
    assert (
        v23.confirmation.validation_boundary
        == "structural_reversal"
    )

    assert v23.confirmation.validate_until_confirmation
    assert v23.confirmation.enforce_candidate_availability

    assert (
        v23.leg.min_atr_multiple
        == v22.leg.min_atr_multiple
        == 2.8
    )
    assert v23.classification.hierarchy_enabled
    assert v22.classification.hierarchy_enabled


def test_v23_stops_validation_at_structural_reversal():
    config = get_config(
        Timeframe.H1,
        version="2.3.0",
        symbol="XAUUSD",
    )

    assert _validation_end_index(
        _pivot(17),
        min_end=13,
        conf_index=22,
        config=config,
    ) == 17


def test_v23_preserves_minimum_hold_period():
    config = get_config(
        Timeframe.H1,
        version="2.3.0",
        symbol="XAUUSD",
    )

    assert _validation_end_index(
        _pivot(11),
        min_end=13,
        conf_index=22,
        config=config,
    ) == 13


def test_v23_missing_boundary_falls_back_to_confirmation():
    config = get_config(
        Timeframe.H1,
        version="2.3.0",
        symbol="XAUUSD",
    )

    assert _validation_end_index(
        _pivot(None),
        min_end=13,
        conf_index=22,
        config=config,
    ) == 22


def test_v22_retains_confirmation_end_validation():
    config = get_config(
        Timeframe.H1,
        version="2.2.0",
        symbol="XAUUSD",
    )

    assert _validation_end_index(
        _pivot(17),
        min_end=13,
        conf_index=22,
        config=config,
    ) == 22

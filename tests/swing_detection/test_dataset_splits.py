"""Locked year-split helpers for swing benchmarks."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from shared.types.models import Candle, Timeframe
from swing_engine.dataset_splits import (
    DatasetSplit,
    assert_not_tuning_locked_test,
    filter_candles_by_split,
    resolve_split,
    split_spec,
)


def _bar(year: int) -> Candle:
    return Candle(
        symbol="EURUSD",
        timeframe=Timeframe.H1,
        timestamp=datetime(year, 6, 1, tzinfo=timezone.utc),
        open=1.1,
        high=1.2,
        low=1.0,
        close=1.15,
        volume=1,
    )


def test_resolve_split_aliases():
    assert resolve_split("train") is DatasetSplit.DEVELOPMENT
    assert resolve_split("validation") is DatasetSplit.VALIDATION
    assert resolve_split("test") is DatasetSplit.LOCKED_TEST


def test_filter_by_year_ranges():
    bars = [_bar(2018), _bar(2022), _bar(2025)]
    assert [c.timestamp.year for c in filter_candles_by_split(bars, "development")] == [2018]
    assert [c.timestamp.year for c in filter_candles_by_split(bars, "validation")] == [2022]
    assert [c.timestamp.year for c in filter_candles_by_split(bars, "locked_test")] == [2025]


def test_locked_test_marked_and_tuning_blocked():
    spec = split_spec("locked_test")
    assert spec.locked is True
    assert "2024" in spec.label
    with pytest.raises(RuntimeError, match="Locked test"):
        assert_not_tuning_locked_test("locked_test", purpose="tune")
    assert_not_tuning_locked_test("locked_test", purpose="evaluate")

"""Locked benchmark year splits for swing evaluation.

Development / training: 2015–2021
Validation:             2022–2023
Locked test:            2024–2026

The locked test split must not be used for algorithm tuning.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Iterable, TypeVar

from shared.types.models import Candle


class DatasetSplit(str, Enum):
    DEVELOPMENT = "development"  # training / development
    VALIDATION = "validation"
    LOCKED_TEST = "locked_test"


SPLIT_YEAR_RANGES: dict[DatasetSplit, tuple[int, int]] = {
    DatasetSplit.DEVELOPMENT: (2015, 2021),
    DatasetSplit.VALIDATION: (2022, 2023),
    DatasetSplit.LOCKED_TEST: (2024, 2026),
}

# Aliases accepted by CLI / scripts
SPLIT_ALIASES: dict[str, DatasetSplit] = {
    "development": DatasetSplit.DEVELOPMENT,
    "dev": DatasetSplit.DEVELOPMENT,
    "train": DatasetSplit.DEVELOPMENT,
    "training": DatasetSplit.DEVELOPMENT,
    "validation": DatasetSplit.VALIDATION,
    "val": DatasetSplit.VALIDATION,
    "valid": DatasetSplit.VALIDATION,
    "locked_test": DatasetSplit.LOCKED_TEST,
    "locked": DatasetSplit.LOCKED_TEST,
    "test": DatasetSplit.LOCKED_TEST,
    "holdout": DatasetSplit.LOCKED_TEST,
}


@dataclass(frozen=True)
class SplitSpec:
    split: DatasetSplit
    year_start: int
    year_end: int  # inclusive
    locked: bool

    @property
    def label(self) -> str:
        kind = "LOCKED TEST" if self.locked else self.split.value.upper()
        return f"{kind} ({self.year_start}–{self.year_end})"


def resolve_split(name: str) -> DatasetSplit:
    key = name.strip().lower()
    if key not in SPLIT_ALIASES:
        raise ValueError(
            f"Unknown dataset split {name!r}. "
            f"Expected one of: {sorted(SPLIT_ALIASES)}"
        )
    return SPLIT_ALIASES[key]


def split_spec(split: DatasetSplit | str) -> SplitSpec:
    resolved = resolve_split(split) if isinstance(split, str) else split
    start, end = SPLIT_YEAR_RANGES[resolved]
    return SplitSpec(
        split=resolved,
        year_start=start,
        year_end=end,
        locked=resolved is DatasetSplit.LOCKED_TEST,
    )


def _utc_year(ts: datetime) -> int:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    else:
        ts = ts.astimezone(timezone.utc)
    return ts.year


T = TypeVar("T")


def filter_by_split_years(
    items: Iterable[T],
    split: DatasetSplit | str,
    *,
    timestamp_attr: str = "timestamp",
) -> list[T]:
    """Keep items whose UTC year falls in the split range (inclusive)."""
    spec = split_spec(split)
    out: list[T] = []
    for item in items:
        ts = getattr(item, timestamp_attr)
        year = _utc_year(ts)
        if spec.year_start <= year <= spec.year_end:
            out.append(item)
    return out


def filter_candles_by_split(
    candles: list[Candle],
    split: DatasetSplit | str,
) -> list[Candle]:
    return filter_by_split_years(candles, split)


def assert_not_tuning_locked_test(split: DatasetSplit | str, *, purpose: str) -> None:
    """Raise if a caller tries to use locked test for tuning."""
    spec = split_spec(split)
    if spec.locked and purpose.lower() in {"tune", "tuning", "optimize", "optimization", "fit"}:
        raise RuntimeError(
            f"Refusing to {purpose} against {spec.label}. "
            "Locked test data must only be used for final evaluation."
        )

"""Market Structure Engine v1 — causal models.

Frozen dataclasses and enums for deterministic structure analysis over
confirmed swings. Does not discover pivots or call the swing engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from shared.types.models import TrendDirection, to_dict
from swing_engine.models import SwingDirection, SwingScope, SwingTier


class StructureRelation(str, Enum):
    HH = "HH"
    HL = "HL"
    LH = "LH"
    LL = "LL"
    EQUAL_HIGH = "EQUAL_HIGH"
    EQUAL_LOW = "EQUAL_LOW"
    UNKNOWN = "UNKNOWN"


class StructureEventType(str, Enum):
    BOS = "BOS"
    CHOCH = "CHOCH"


@dataclass(frozen=True)
class StructureDetectorConfig:
    """Named configuration for the v1 structure detector."""

    # Absolute price equality tolerance for EQUAL_HIGH / EQUAL_LOW.
    price_equality_tolerance: float = 1e-9

    def __post_init__(self) -> None:
        tol = self.price_equality_tolerance
        if isinstance(tol, bool) or not isinstance(tol, (int, float)):
            raise ValueError("price_equality_tolerance must be a finite number")
        # Local import avoided: math used by callers; keep validation here.
        import math

        if not math.isfinite(float(tol)) or float(tol) < 0:
            raise ValueError(
                "price_equality_tolerance must be finite and non-negative"
            )


@dataclass(frozen=True)
class ProjectedSwingFact:
    """One causally projected structural fact derived from a DetectedSwing.

    Availability is fixed at construction and never depends on as_of_index.
    Dual-phase hierarchy swings emit a first-level INTERNAL fact and a later
    EXTERNAL fact with distinct swing_ids.
    """

    swing_id: str
    source_swing_id: str
    pivot_index: int
    confirmation_index: int
    direction: SwingDirection
    tier: SwingTier
    scope: SwingScope
    price: float
    available_index: int
    phase: str  # "first_level" | "hierarchy_external" | "supplied_external"

    def to_dict(self) -> dict[str, Any]:
        return {
            "swing_id": self.swing_id,
            "source_swing_id": self.source_swing_id,
            "pivot_index": self.pivot_index,
            "confirmation_index": self.confirmation_index,
            "direction": self.direction.value,
            "tier": self.tier.value,
            "scope": self.scope.value,
            "price": self.price,
            "available_index": self.available_index,
            "phase": self.phase,
        }


@dataclass(frozen=True)
class StructureSwingRelation:
    swing_id: str
    pivot_index: int
    confirmation_index: int
    direction: SwingDirection
    tier: SwingTier
    scope: SwingScope
    price: float
    relation: StructureRelation
    previous_same_direction_swing_id: str | None
    available_index: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "swing_id": self.swing_id,
            "pivot_index": self.pivot_index,
            "confirmation_index": self.confirmation_index,
            "direction": self.direction.value,
            "tier": self.tier.value,
            "scope": self.scope.value,
            "price": self.price,
            "relation": self.relation.value,
            "previous_same_direction_swing_id": (
                self.previous_same_direction_swing_id
            ),
            "available_index": self.available_index,
        }


@dataclass(frozen=True)
class StructureEvent:
    event_id: str
    event_type: StructureEventType
    direction: TrendDirection
    scope: SwingScope
    level_swing_id: str
    level_pivot_index: int
    level_price: float
    level_available_index: int
    break_index: int
    break_timestamp: datetime
    break_close: float
    prior_bias: TrendDirection
    resulting_bias: TrendDirection
    pending_bias: TrendDirection
    is_continuation: bool
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "direction": self.direction.value,
            "scope": self.scope.value,
            "level_swing_id": self.level_swing_id,
            "level_pivot_index": self.level_pivot_index,
            "level_price": self.level_price,
            "level_available_index": self.level_available_index,
            "break_index": self.break_index,
            "break_timestamp": self.break_timestamp.isoformat(),
            "break_close": self.break_close,
            "prior_bias": self.prior_bias.value,
            "resulting_bias": self.resulting_bias.value,
            "pending_bias": self.pending_bias.value,
            "is_continuation": self.is_continuation,
            "metadata": to_dict(dict(sorted(self.metadata.items()))),
        }


@dataclass(frozen=True)
class StructureLevel:
    """Active breakable structural level."""

    swing_id: str
    pivot_index: int
    price: float
    direction: SwingDirection
    scope: SwingScope
    available_index: int
    broken: bool = False
    break_index: int | None = None


@dataclass(frozen=True)
class StructureSnapshot:
    as_of_index: int
    external_bias: TrendDirection
    pending_external_bias: TrendDirection
    internal_bias: TrendDirection
    pending_internal_bias: TrendDirection
    swing_relations: tuple[StructureSwingRelation, ...]
    events: tuple[StructureEvent, ...]
    latest_external_high: float | None
    latest_external_low: float | None
    latest_internal_high: float | None
    latest_internal_low: float | None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "as_of_index": self.as_of_index,
            "external_bias": self.external_bias.value,
            "pending_external_bias": self.pending_external_bias.value,
            "internal_bias": self.internal_bias.value,
            "pending_internal_bias": self.pending_internal_bias.value,
            "swing_relations": [r.to_dict() for r in self.swing_relations],
            "events": [e.to_dict() for e in self.events],
            "latest_external_high": self.latest_external_high,
            "latest_external_low": self.latest_external_low,
            "latest_internal_high": self.latest_internal_high,
            "latest_internal_low": self.latest_internal_low,
            "metadata": to_dict(dict(sorted(self.metadata.items()))),
        }


class StructureInputError(ValueError):
    """Invalid candles/confirmed-swing contract for structure analysis."""

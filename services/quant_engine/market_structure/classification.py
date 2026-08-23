"""Explainable HH/HL/LH/LL classifications from a StructureSnapshot.

Relations are already computed causally by the detector (same-direction,
same-scope comparison only). This module exposes human-readable records
without re-running swing detection.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from swing_engine.models import SwingDirection, SwingScope

from services.quant_engine.market_structure.models import (
    StructureRelation,
    StructureSnapshot,
    StructureSwingRelation,
)


@dataclass(frozen=True)
class SwingClassificationRecord:
    """One classified confirmed swing vs its previous comparable swing."""

    swing_id: str
    direction: str  # HIGH | LOW
    scope: str
    classification: str  # HH | HL | LH | LL | EQUAL_HIGH | EQUAL_LOW | UNKNOWN
    pivot_index: int
    price: float
    available_index: int
    previous_comparable_swing_id: str | None
    previous_price: float | None
    price_difference: float | None
    symbol: str | None
    timeframe: str | None
    swing_engine_version: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "swing_id": self.swing_id,
            "direction": self.direction,
            "scope": self.scope,
            "classification": self.classification,
            "pivot_index": self.pivot_index,
            "price": self.price,
            "available_index": self.available_index,
            "previous_comparable_swing_id": self.previous_comparable_swing_id,
            "previous_price": self.previous_price,
            "price_difference": self.price_difference,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "swing_engine_version": self.swing_engine_version,
        }


def _prev_price(
    relations: tuple[StructureSwingRelation, ...],
    previous_id: str | None,
) -> float | None:
    if previous_id is None:
        return None
    for rel in relations:
        if rel.swing_id == previous_id:
            return float(rel.price)
    return None


def explain_swing_classifications(
    snapshot: StructureSnapshot,
    *,
    symbol: str | None = None,
    timeframe: str | None = None,
    swing_engine_version: str | None = None,
    scope: SwingScope | None = SwingScope.EXTERNAL,
) -> list[SwingClassificationRecord]:
    """Build explainable classification records from snapshot relations."""

    version = swing_engine_version or str(
        (snapshot.metadata or {}).get("swing_engine_version") or ""
    ) or None
    out: list[SwingClassificationRecord] = []
    for rel in snapshot.swing_relations:
        if scope is not None and rel.scope is not scope:
            continue
        prev_id = rel.previous_same_direction_swing_id
        prev_px = _prev_price(snapshot.swing_relations, prev_id)
        diff = None if prev_px is None else float(rel.price) - float(prev_px)
        out.append(
            SwingClassificationRecord(
                swing_id=rel.swing_id,
                direction=rel.direction.value,
                scope=rel.scope.value,
                classification=rel.relation.value,
                pivot_index=rel.pivot_index,
                price=float(rel.price),
                available_index=rel.available_index,
                previous_comparable_swing_id=prev_id,
                previous_price=prev_px,
                price_difference=diff,
                symbol=symbol,
                timeframe=timeframe,
                swing_engine_version=version,
            )
        )
    return out


def last_classification(
    records: list[SwingClassificationRecord],
    direction: SwingDirection,
) -> StructureRelation | None:
    for record in reversed(records):
        if record.direction == direction.value:
            try:
                return StructureRelation(record.classification)
            except ValueError:
                return None
    return None

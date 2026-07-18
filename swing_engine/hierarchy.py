"""Recursive structural hierarchy for already-confirmed first-level swings.

The v2.1 detector deliberately solves pivot location first.  This module adds a
second, slower directional-change layer that classifies the structural role of
those stable pivots without changing their price, timestamp, or confirmation
bar.

Hierarchy is revision-aware:

* CONFIRMED_MAJOR -- a later opposite swing moved far enough to confirm the
  pivot as a higher-order structural anchor.
* PROVISIONAL_MAJOR -- the current pending extreme is prominent enough to be
  exposed as major, but may still be superseded.
* SUPERSEDED -- a pending same-direction extreme was replaced by a more extreme
  pivot before higher-order confirmation.
* INTERNAL -- the pivot never became the active higher-order extreme.
* PENDING -- the current higher-order extreme is not prominent enough for
  provisional-major status.

Only hierarchy labels can revise.  First-level swing location and confirmation
remain unchanged.
"""

from __future__ import annotations

from collections.abc import Sequence

from swing_engine.config import SwingEngineConfig
from swing_engine.models import (
    DetectedSwing,
    SwingDirection,
    SwingHierarchyState,
    SwingScope,
    SwingTier,
)


def apply_recursive_hierarchy(
    swings: list[DetectedSwing],
    atr_series: Sequence[float],
    config: SwingEngineConfig,
) -> list[DetectedSwing]:
    """Classify a second structural level over confirmed first-level swings.

    The input order is preserved.  Unconfirmed swings are retained but excluded
    from hierarchy transitions.  The function mutates the supplied swing
    objects, matching the rest of the scoring pipeline.
    """

    classification = config.classification
    if not classification.hierarchy_enabled:
        return swings

    threshold = float(classification.hierarchy_reversal_atr)
    provisional_threshold = float(
        classification.hierarchy_provisional_prominence_atr
    )
    if threshold <= 0:
        raise ValueError("hierarchy_reversal_atr must be positive")
    if provisional_threshold < 0:
        raise ValueError(
            "hierarchy_provisional_prominence_atr cannot be negative"
        )
    if classification.hierarchy_scope_policy != "major_external":
        raise ValueError(
            "Unsupported hierarchy_scope_policy: "
            f"{classification.hierarchy_scope_policy!r}"
        )

    confirmed = [swing for swing in swings if swing.confirmed]
    for swing in swings:
        _reset_hierarchy(swing, threshold, classification.hierarchy_scope_policy)

    if not confirmed:
        return swings

    pending = confirmed[0]
    _mark_pending(pending, config)

    for candidate in confirmed[1:]:
        if candidate.direction is pending.direction:
            if _is_more_extreme(candidate, pending):
                _mark_superseded(pending, candidate)
                pending = candidate
                _mark_pending(pending, config)
            else:
                _mark_internal(
                    candidate,
                    pending,
                    reason="less_extreme_same_direction",
                )
            continue

        reversal_atr = _reversal_atr(pending, candidate, atr_series)
        candidate.metadata["hierarchy_test_anchor_index"] = pending.pivot_index
        candidate.metadata["hierarchy_test_reversal_atr"] = round(
            reversal_atr, 4
        )

        if reversal_atr >= threshold:
            _mark_confirmed_major(
                pending,
                candidate,
                reversal_atr,
                config,
            )
            pending = candidate
            _mark_pending(pending, config)
        else:
            _mark_internal(
                candidate,
                pending,
                reason="insufficient_hierarchy_reversal",
                reversal_atr=reversal_atr,
            )

    prominence = float(
        pending.metadata.get("structural_prominence_atr", 0.0) or 0.0
    )
    if (
        classification.hierarchy_include_provisional
        and prominence >= provisional_threshold
    ):
        _mark_provisional_major(pending, prominence, config)
    else:
        pending.tier = SwingTier.MINOR
        pending.scope = SwingScope.INTERNAL
        pending.hierarchy_state = SwingHierarchyState.PENDING
        pending.metadata.update(
            {
                "hierarchy_state": SwingHierarchyState.PENDING.value,
                "hierarchy_pending_prominence_atr": round(prominence, 4),
                "hierarchy_provisional_threshold_atr": provisional_threshold,
            }
        )

    return swings


def _reset_hierarchy(
    swing: DetectedSwing,
    threshold: float,
    scope_policy: str,
) -> None:
    swing.tier = SwingTier.MINOR
    swing.scope = SwingScope.INTERNAL
    swing.hierarchy_state = (
        SwingHierarchyState.PENDING
        if swing.confirmed
        else SwingHierarchyState.INTERNAL
    )
    swing.hierarchy_confirmation_index = None
    swing.hierarchy_revision_index = None
    swing.metadata.update(
        {
            "hierarchy_algorithm": "recursive_directional_change",
            "hierarchy_reversal_threshold_atr": threshold,
            "hierarchy_scope_policy": scope_policy,
            "hierarchy_state": swing.hierarchy_state.value,
            "hierarchy_available_index": _availability_index(swing),
            "hierarchy_confirmation_index": None,
            "hierarchy_revision_index": None,
        }
    )


def _mark_pending(
    swing: DetectedSwing,
    config: SwingEngineConfig,
) -> None:
    swing.tier = SwingTier.MINOR
    swing.scope = SwingScope.INTERNAL
    swing.hierarchy_state = SwingHierarchyState.PENDING
    prominence = float(
        swing.metadata.get("structural_prominence_atr", 0.0) or 0.0
    )
    provisionally_eligible = (
        config.classification.hierarchy_include_provisional
        and prominence
        >= config.classification.hierarchy_provisional_prominence_atr
    )
    swing.metadata.update(
        {
            "hierarchy_state": SwingHierarchyState.PENDING.value,
            "hierarchy_anchor_pivot_index": swing.pivot_index,
            "hierarchy_was_provisional": provisionally_eligible,
            "hierarchy_provisional_since_index": (
                _availability_index(swing)
                if provisionally_eligible
                else None
            ),
        }
    )


def _mark_internal(
    swing: DetectedSwing,
    anchor: DetectedSwing,
    *,
    reason: str,
    reversal_atr: float | None = None,
) -> None:
    swing.tier = SwingTier.MINOR
    swing.scope = SwingScope.INTERNAL
    swing.hierarchy_state = SwingHierarchyState.INTERNAL
    swing.metadata.update(
        {
            "hierarchy_state": SwingHierarchyState.INTERNAL.value,
            "hierarchy_reason": reason,
            "hierarchy_anchor_pivot_index": anchor.pivot_index,
        }
    )
    if reversal_atr is not None:
        swing.metadata["hierarchy_reversal_atr"] = round(reversal_atr, 4)


def _mark_superseded(
    swing: DetectedSwing,
    superseder: DetectedSwing,
) -> None:
    revision_index = max(
        _availability_index(swing),
        _availability_index(superseder),
    )
    swing.tier = SwingTier.MINOR
    swing.scope = SwingScope.INTERNAL
    swing.hierarchy_state = SwingHierarchyState.SUPERSEDED
    swing.hierarchy_revision_index = revision_index
    swing.metadata.update(
        {
            "hierarchy_state": SwingHierarchyState.SUPERSEDED.value,
            "hierarchy_reason": "more_extreme_same_direction",
            "hierarchy_superseded_by_index": superseder.pivot_index,
            "hierarchy_revision_index": revision_index,
        }
    )


def _mark_confirmed_major(
    swing: DetectedSwing,
    confirmer: DetectedSwing,
    reversal_atr: float,
    config: SwingEngineConfig,
) -> None:
    confirmation_index = max(
        _availability_index(swing),
        _availability_index(confirmer),
    )
    swing.tier = SwingTier.MAJOR
    swing.scope = _major_scope(swing, config)
    swing.hierarchy_state = SwingHierarchyState.CONFIRMED_MAJOR
    swing.hierarchy_confirmation_index = confirmation_index
    swing.metadata.update(
        {
            "hierarchy_state": SwingHierarchyState.CONFIRMED_MAJOR.value,
            "hierarchy_confirmation_index": confirmation_index,
            "hierarchy_reversal_atr": round(reversal_atr, 4),
            "hierarchy_reversal_pivot_index": confirmer.pivot_index,
            "hierarchy_reversal_price": confirmer.price,
            "hierarchy_reversal_direction": confirmer.direction.value,
        }
    )


def _mark_provisional_major(
    swing: DetectedSwing,
    prominence: float,
    config: SwingEngineConfig,
) -> None:
    swing.tier = SwingTier.MAJOR
    swing.scope = _major_scope(swing, config)
    swing.hierarchy_state = SwingHierarchyState.PROVISIONAL_MAJOR
    swing.hierarchy_confirmation_index = None
    swing.metadata.update(
        {
            "hierarchy_state": SwingHierarchyState.PROVISIONAL_MAJOR.value,
            "hierarchy_pending_prominence_atr": round(prominence, 4),
            "hierarchy_confirmation_index": None,
            "hierarchy_is_revisable": True,
        }
    )


def _major_scope(
    swing: DetectedSwing,
    config: SwingEngineConfig,
) -> SwingScope:
    """Assign scope independently from the tier-selection routine.

    v2.2 uses a conservative two-scope policy: higher-order anchors are
    external and all first-level pivots are internal.  The separate function
    and config key intentionally leave room for a future protected-range scope
    model without coupling it back into tier selection.
    """

    policy = config.classification.hierarchy_scope_policy
    if policy == "major_external":
        return SwingScope.EXTERNAL
    raise ValueError(f"Unsupported hierarchy_scope_policy: {policy!r}")


def _is_more_extreme(
    candidate: DetectedSwing,
    pending: DetectedSwing,
) -> bool:
    if candidate.direction is SwingDirection.HIGH:
        return candidate.price >= pending.price
    return candidate.price <= pending.price


def _reversal_atr(
    pending: DetectedSwing,
    opposite: DetectedSwing,
    atr_series: Sequence[float],
) -> float:
    atr = _atr_at(pending.pivot_index, atr_series)
    return abs(opposite.price - pending.price) / atr if atr > 0 else 0.0


def _atr_at(index: int, atr_series: Sequence[float]) -> float:
    if not atr_series:
        return 0.0

    bounded = min(max(index, 0), len(atr_series) - 1)
    value = float(atr_series[bounded])
    if value > 0:
        return value

    for prior in range(bounded - 1, -1, -1):
        value = float(atr_series[prior])
        if value > 0:
            return value

    for later in range(bounded + 1, len(atr_series)):
        value = float(atr_series[later])
        if value > 0:
            return value

    return 0.0


def _availability_index(swing: DetectedSwing) -> int:
    if swing.confirmation_index is not None:
        return int(swing.confirmation_index)

    available = swing.metadata.get("available_index")
    if available is not None:
        return int(available)

    return int(swing.pivot_index)

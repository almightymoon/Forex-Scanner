"""Market Structure Engine v1 — causal detector.

Consumes confirmed swings supplied by the caller. Does not construct a swing
engine instance, does not load swing YAML configuration, and never looks past
as_of_index.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

from shared.types.models import Candle, TrendDirection
from swing_engine.models import DetectedSwing, SwingDirection, SwingScope, SwingTier

from services.quant_engine.market_structure.models import (
    ProjectedSwingFact,
    StructureDetectorConfig,
    StructureEvent,
    StructureEventType,
    StructureInputError,
    StructureLevel,
    StructureRelation,
    StructureSnapshot,
    StructureSwingRelation,
)


def swing_id_for(swing: DetectedSwing) -> str:
    """Stable identity derived from structural facts (no random UUIDs)."""

    return f"{swing.direction.value}:{int(swing.pivot_index)}"


def event_id_for(
    *,
    scope: SwingScope,
    event_type: StructureEventType,
    direction: TrendDirection,
    level_pivot_index: int,
    break_index: int,
) -> str:
    return (
        f"{scope.value}:{event_type.value}:{direction.value}:"
        f"{level_pivot_index}:{break_index}"
    )


def structural_available_index(swing: DetectedSwing) -> int:
    """First-level structural availability (confirmation_index).

    Monotonic: does not depend on as_of_index. Hierarchy promotion creates a
    separate projected fact (see :func:`project_swing_facts`) rather than
    moving this index.
    """

    if swing.confirmation_index is None:
        raise StructureInputError("missing confirmation_index")
    return int(swing.confirmation_index)


def project_swing_facts(swing: DetectedSwing) -> tuple[ProjectedSwingFact, ...]:
    """Project a DetectedSwing into causal structural facts.

    DetectedSwing hierarchy lifecycle (v2.2+ / v2.3):

    * First-level confirmation freezes pivot/price/direction at
      ``confirmation_index`` while hierarchy resets tier/scope to
      MINOR/INTERNAL.
    * Later, ``hierarchy_confirmation_index`` records when a swing is promoted
      to CONFIRMED_MAJOR (MAJOR + EXTERNAL under major_external policy).
    * PROVISIONAL_MAJOR has no ``hierarchy_confirmation_index`` and is not a
      frozen external anchor.

    Causal projection chosen for Market Structure Engine v1:

    1. Always emit a first-level fact available at ``confirmation_index``.
       When ``hierarchy_confirmation_index`` is set, that first-level fact is
       INTERNAL/MINOR even if the final DetectedSwing labels are EXTERNAL/MAJOR
       (do not consume final hierarchy labels early).
    2. When ``hierarchy_confirmation_index`` is set, emit a second EXTERNAL/MAJOR
       fact available exactly at that index. Earlier INTERNAL history is kept.
    3. When ``hierarchy_confirmation_index`` is absent and the caller already
       supplied EXTERNAL (or MAJOR) labels, emit a single supplied-external fact
       at ``confirmation_index`` (no delayed promotion in the input).
    4. Otherwise emit a single INTERNAL fact at ``confirmation_index`` using the
       supplied INTERNAL/MINOR labels (or INTERNAL/MINOR defaults).

    Each fact's ``available_index`` is fixed at projection time and never
    changes when ``as_of_index`` increases. Callers filter by
    ``available_index <= as_of_index``.
    """

    if swing.confirmation_index is None:
        raise StructureInputError("missing confirmation_index")

    conf = int(swing.confirmation_index)
    pivot = int(swing.pivot_index)
    source_id = swing_id_for(swing)
    price = float(swing.price)
    direction = swing.direction
    hierarchy = swing.hierarchy_confirmation_index

    if hierarchy is not None:
        hier = int(hierarchy)
        first = ProjectedSwingFact(
            swing_id=source_id,
            source_swing_id=source_id,
            pivot_index=pivot,
            confirmation_index=conf,
            direction=direction,
            tier=SwingTier.MINOR,
            scope=SwingScope.INTERNAL,
            price=price,
            available_index=conf,
            phase="first_level",
        )
        external = ProjectedSwingFact(
            swing_id=f"{source_id}:EXTERNAL",
            source_swing_id=source_id,
            pivot_index=pivot,
            confirmation_index=conf,
            direction=direction,
            tier=SwingTier.MAJOR,
            scope=SwingScope.EXTERNAL,
            price=price,
            available_index=hier,
            phase="hierarchy_external",
        )
        return (first, external)

    # No delayed hierarchy confirmation on this input object.
    if swing.scope is SwingScope.EXTERNAL or swing.tier is SwingTier.MAJOR:
        return (
            ProjectedSwingFact(
                swing_id=source_id,
                source_swing_id=source_id,
                pivot_index=pivot,
                confirmation_index=conf,
                direction=direction,
                tier=swing.tier if isinstance(swing.tier, SwingTier) else SwingTier.MAJOR,
                scope=SwingScope.EXTERNAL,
                price=price,
                available_index=conf,
                phase="supplied_external",
            ),
        )

    return (
        ProjectedSwingFact(
            swing_id=source_id,
            source_swing_id=source_id,
            pivot_index=pivot,
            confirmation_index=conf,
            direction=direction,
            tier=swing.tier if isinstance(swing.tier, SwingTier) else SwingTier.MINOR,
            scope=SwingScope.INTERNAL,
            price=price,
            available_index=conf,
            phase="first_level",
        ),
    )


def _is_finite_number(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(float(value))


def _validate_config(config: StructureDetectorConfig) -> StructureDetectorConfig:
    # __post_init__ already validates; re-check for safety if constructed oddly.
    tol = config.price_equality_tolerance
    if not _is_finite_number(tol) or float(tol) < 0:
        raise StructureInputError(
            "price_equality_tolerance must be finite and non-negative"
        )
    return config


def _validate_and_sort_swings(
    candles: list[Candle],
    confirmed_swings: list[DetectedSwing],
    *,
    as_of_index: int,
) -> list[DetectedSwing]:
    if as_of_index < -1:
        raise StructureInputError(f"invalid as_of_index: {as_of_index}")
    if as_of_index >= len(candles) and candles:
        raise StructureInputError(
            f"as_of_index {as_of_index} beyond candle prefix "
            f"(len={len(candles)})"
        )

    seen: dict[str, DetectedSwing] = {}
    accepted: list[DetectedSwing] = []
    for swing in confirmed_swings:
        if not isinstance(swing.direction, SwingDirection):
            raise StructureInputError("invalid swing direction")
        if not isinstance(swing.tier, SwingTier):
            raise StructureInputError(
                f"swing {swing_id_for(swing)} has invalid tier"
            )
        if not isinstance(swing.scope, SwingScope):
            raise StructureInputError(
                f"swing {swing_id_for(swing)} has invalid scope"
            )
        if swing.confirmation_index is None:
            raise StructureInputError(
                f"swing {swing_id_for(swing)} missing confirmation_index"
            )
        conf = int(swing.confirmation_index)
        pivot = int(swing.pivot_index)
        if conf < pivot:
            raise StructureInputError(
                f"swing {swing_id_for(swing)} confirmation_index {conf} "
                f"earlier than pivot_index {pivot}"
            )
        if conf > as_of_index:
            raise StructureInputError(
                f"swing {swing_id_for(swing)} confirmation_index {conf} "
                f"beyond as_of_index {as_of_index}"
            )
        if pivot < 0 or pivot > as_of_index or pivot >= len(candles):
            raise StructureInputError(
                f"swing {swing_id_for(swing)} pivot_index {pivot} outside "
                f"candle prefix"
            )
        if not _is_finite_number(swing.price):
            raise StructureInputError(
                f"swing {swing_id_for(swing)} has invalid price"
            )
        hierarchy = swing.hierarchy_confirmation_index
        if hierarchy is not None:
            hier = int(hierarchy)
            if hier < conf:
                raise StructureInputError(
                    f"swing {swing_id_for(swing)} hierarchy_confirmation_index "
                    f"{hier} earlier than confirmation_index {conf}"
                )
        sid = swing_id_for(swing)
        prior = seen.get(sid)
        if prior is not None:
            if (
                prior.price != swing.price
                or prior.confirmation_index != swing.confirmation_index
                or prior.direction != swing.direction
                or prior.tier != swing.tier
                or prior.scope != swing.scope
                or prior.hierarchy_confirmation_index
                != swing.hierarchy_confirmation_index
            ):
                raise StructureInputError(
                    f"duplicate swing_id {sid} with conflicting data"
                )
            continue
        seen[sid] = swing
        accepted.append(swing)

    accepted.sort(
        key=lambda s: (
            int(s.confirmation_index or 0),
            int(s.pivot_index),
            s.direction.value,
        )
    )
    return accepted


def _classify_relation(
    *,
    direction: SwingDirection,
    price: float,
    previous_price: float | None,
    tolerance: float,
) -> StructureRelation:
    if previous_price is None:
        return StructureRelation.UNKNOWN
    delta = price - previous_price
    if abs(delta) <= tolerance:
        return (
            StructureRelation.EQUAL_HIGH
            if direction is SwingDirection.HIGH
            else StructureRelation.EQUAL_LOW
        )
    if direction is SwingDirection.HIGH:
        return StructureRelation.HH if delta > 0 else StructureRelation.LH
    return StructureRelation.HL if delta > 0 else StructureRelation.LL


@dataclass
class _TrackState:
    bias: TrendDirection = TrendDirection.RANGING
    pending_bias: TrendDirection = TrendDirection.RANGING
    levels: list[StructureLevel] = None  # type: ignore[assignment]
    events: list[StructureEvent] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.levels is None:
            self.levels = []
        if self.events is None:
            self.events = []


def _transition_for_break(
    track: _TrackState,
    *,
    break_direction: TrendDirection,
) -> tuple[StructureEventType, TrendDirection, TrendDirection, bool]:
    """Pure state-machine step; does not mutate track."""

    prior_bias = track.bias
    pending = track.pending_bias
    event_type = StructureEventType.BOS
    resulting = prior_bias
    new_pending = pending
    is_continuation = False

    if prior_bias is TrendDirection.RANGING and pending is TrendDirection.RANGING:
        event_type = StructureEventType.BOS
        resulting = break_direction
        new_pending = TrendDirection.RANGING
        is_continuation = False
    elif pending is not TrendDirection.RANGING:
        if break_direction is pending:
            event_type = StructureEventType.BOS
            resulting = pending
            new_pending = TrendDirection.RANGING
            is_continuation = False
        else:
            event_type = StructureEventType.BOS
            resulting = prior_bias
            new_pending = TrendDirection.RANGING
            is_continuation = True
    elif break_direction is prior_bias:
        event_type = StructureEventType.BOS
        resulting = prior_bias
        new_pending = TrendDirection.RANGING
        is_continuation = True
    else:
        event_type = StructureEventType.CHOCH
        resulting = prior_bias
        new_pending = break_direction
        is_continuation = False

    return event_type, resulting, new_pending, is_continuation


def _emit_break_event(
    track: _TrackState,
    *,
    scope: SwingScope,
    level: StructureLevel,
    break_index: int,
    break_timestamp,
    break_close: float,
    break_direction: TrendDirection,
    event_type: StructureEventType,
    prior_bias: TrendDirection,
    resulting: TrendDirection,
    new_pending: TrendDirection,
    is_continuation: bool,
    retired_level_ids: tuple[str, ...],
) -> None:
    event = StructureEvent(
        event_id=event_id_for(
            scope=scope,
            event_type=event_type,
            direction=break_direction,
            level_pivot_index=level.pivot_index,
            break_index=break_index,
        ),
        event_type=event_type,
        direction=break_direction,
        scope=scope,
        level_swing_id=level.swing_id,
        level_pivot_index=level.pivot_index,
        level_price=level.price,
        level_available_index=level.available_index,
        break_index=break_index,
        break_timestamp=break_timestamp,
        break_close=break_close,
        prior_bias=prior_bias,
        resulting_bias=resulting,
        pending_bias=new_pending,
        is_continuation=is_continuation,
        metadata={
            "level_direction": level.direction.value,
            "close_break": True,
            "retired_level_swing_ids": list(retired_level_ids),
        },
    )
    track.events.append(event)
    track.bias = resulting
    track.pending_bias = new_pending


def analyze_structure(
    candles: list[Candle],
    confirmed_swings: list[DetectedSwing],
    *,
    as_of_index: int | None = None,
    config: StructureDetectorConfig | None = None,
) -> StructureSnapshot:
    """Analyze market structure from a candle prefix and confirmed swings.

    Parameters
    ----------
    candles:
        Candle prefix. Events never inspect candles after ``as_of_index``.
    confirmed_swings:
        Confirmed swings for the same prefix (caller responsibility).
    as_of_index:
        Inclusive last candle index. Defaults to ``len(candles) - 1``.
    config:
        Detector configuration (equality tolerance).
    """

    cfg = _validate_config(
        config if config is not None else StructureDetectorConfig()
    )
    if not candles:
        if as_of_index is not None and as_of_index != -1:
            raise StructureInputError(
                "empty candles only allow as_of_index=-1 or omitted"
            )
        if confirmed_swings:
            raise StructureInputError(
                "confirmed swings supplied with empty candle list"
            )
        return StructureSnapshot(
            as_of_index=-1,
            external_bias=TrendDirection.RANGING,
            pending_external_bias=TrendDirection.RANGING,
            internal_bias=TrendDirection.RANGING,
            pending_internal_bias=TrendDirection.RANGING,
            swing_relations=(),
            events=(),
            latest_external_high=None,
            latest_external_low=None,
            latest_internal_high=None,
            latest_internal_low=None,
            metadata={"empty": True},
        )

    end = len(candles) - 1 if as_of_index is None else int(as_of_index)
    if end < 0 or end >= len(candles):
        raise StructureInputError(f"as_of_index {end} out of range")

    prefix = candles[: end + 1]
    for idx, candle in enumerate(prefix):
        if not _is_finite_number(candle.close):
            raise StructureInputError(
                f"non-finite candle close at index {idx}"
            )

    swings = _validate_and_sort_swings(
        prefix, confirmed_swings, as_of_index=end
    )

    # Project causal facts; availability is fixed per fact (monotonic).
    facts: list[ProjectedSwingFact] = []
    for swing in swings:
        for fact in project_swing_facts(swing):
            if fact.available_index <= end:
                facts.append(fact)

    facts.sort(
        key=lambda f: (
            f.available_index,
            f.pivot_index,
            f.direction.value,
            f.scope.value,
            f.swing_id,
        )
    )

    last_same: dict[tuple[SwingScope, SwingDirection], StructureSwingRelation] = {}
    relations: list[StructureSwingRelation] = []

    for fact in facts:
        if fact.scope not in (SwingScope.EXTERNAL, SwingScope.INTERNAL):
            continue
        prev = last_same.get((fact.scope, fact.direction))
        relation = _classify_relation(
            direction=fact.direction,
            price=fact.price,
            previous_price=None if prev is None else prev.price,
            tolerance=cfg.price_equality_tolerance,
        )
        item = StructureSwingRelation(
            swing_id=fact.swing_id,
            pivot_index=fact.pivot_index,
            confirmation_index=fact.confirmation_index,
            direction=fact.direction,
            tier=fact.tier,
            scope=fact.scope,
            price=fact.price,
            relation=relation,
            previous_same_direction_swing_id=(
                None if prev is None else prev.swing_id
            ),
            available_index=fact.available_index,
        )
        relations.append(item)
        last_same[(fact.scope, fact.direction)] = item

    external = _TrackState()
    internal = _TrackState()

    pending_levels: list[tuple[int, StructureLevel, SwingScope]] = []
    for rel in relations:
        level = StructureLevel(
            swing_id=rel.swing_id,
            pivot_index=rel.pivot_index,
            price=rel.price,
            direction=rel.direction,
            scope=rel.scope,
            available_index=rel.available_index,
        )
        if rel.scope is SwingScope.EXTERNAL:
            if rel.tier is SwingTier.MAJOR:
                pending_levels.append(
                    (rel.available_index, level, SwingScope.EXTERNAL)
                )
        elif rel.scope is SwingScope.INTERNAL:
            pending_levels.append(
                (rel.available_index, level, SwingScope.INTERNAL)
            )

    pending_levels.sort(
        key=lambda item: (
            item[0],
            item[1].pivot_index,
            item[1].direction.value,
            item[1].swing_id,
        )
    )

    active_ext: list[StructureLevel] = []
    active_int: list[StructureLevel] = []
    level_iter = 0

    for idx, candle in enumerate(prefix):
        while (
            level_iter < len(pending_levels)
            and pending_levels[level_iter][0] <= idx
        ):
            _, level, scope = pending_levels[level_iter]
            if scope is SwingScope.EXTERNAL:
                active_ext.append(level)
                external.levels.append(level)
            else:
                active_int.append(level)
                internal.levels.append(level)
            level_iter += 1

        close = float(candle.close)
        active_ext = _scan_breaks_atomic(
            track=external,
            scope=SwingScope.EXTERNAL,
            levels=active_ext,
            idx=idx,
            candle=candle,
            close=close,
        )
        active_int = _scan_breaks_atomic(
            track=internal,
            scope=SwingScope.INTERNAL,
            levels=active_int,
            idx=idx,
            candle=candle,
            close=close,
        )

    def _latest(scope: SwingScope, direction: SwingDirection) -> float | None:
        key = (scope, direction)
        item = last_same.get(key)
        return None if item is None else item.price

    all_events = sorted(
        external.events + internal.events,
        key=lambda e: (e.break_index, e.scope.value, e.event_id),
    )
    return StructureSnapshot(
        as_of_index=end,
        external_bias=external.bias,
        pending_external_bias=external.pending_bias,
        internal_bias=internal.bias,
        pending_internal_bias=internal.pending_bias,
        swing_relations=tuple(relations),
        events=tuple(all_events),
        latest_external_high=_latest(SwingScope.EXTERNAL, SwingDirection.HIGH),
        latest_external_low=_latest(SwingScope.EXTERNAL, SwingDirection.LOW),
        latest_internal_high=_latest(SwingScope.INTERNAL, SwingDirection.HIGH),
        latest_internal_low=_latest(SwingScope.INTERNAL, SwingDirection.LOW),
        metadata={
            "detector": "market_structure_v1",
            "price_equality_tolerance": cfg.price_equality_tolerance,
            "confirmed_swing_count": len(swings),
            "projected_fact_count": len(facts),
        },
    )


def _level_crossed(
    level: StructureLevel,
    *,
    idx: int,
    close: float,
) -> bool:
    """True when close breaks the level and break_index > available_index."""

    if level.broken:
        return False
    # Same-candle activation must not break: require strictly later candle.
    if idx <= level.available_index:
        return False
    if level.direction is SwingDirection.HIGH:
        return close > level.price
    return close < level.price


def _scan_breaks_atomic(
    *,
    track: _TrackState,
    scope: SwingScope,
    levels: list[StructureLevel],
    idx: int,
    candle: Candle,
    close: float,
) -> list[StructureLevel]:
    """Process all close breaks for one scope on one candle atomically.

    - Gather all newly crossed highs and lows.
    - Retire every crossed level (no later duplicate events).
    - Emit at most one bullish and one bearish transition.
    - Representative bullish level: highest crossed high.
    - Representative bearish level: lowest crossed low.
    - CHOCH cannot be confirmed by BOS at the same break_index.
    """

    ordered = sorted(
        levels,
        key=lambda level: (
            level.available_index,
            level.pivot_index,
            level.direction.value,
            level.swing_id,
        ),
    )

    crossed_highs: list[StructureLevel] = []
    crossed_lows: list[StructureLevel] = []
    for level in ordered:
        if _level_crossed(level, idx=idx, close=close):
            if level.direction is SwingDirection.HIGH:
                crossed_highs.append(level)
            else:
                crossed_lows.append(level)

    retired_ids_high = tuple(level.swing_id for level in crossed_highs)
    retired_ids_low = tuple(level.swing_id for level in crossed_lows)
    crossed_ids = set(retired_ids_high) | set(retired_ids_low)

    # Mark every crossed level broken before emitting transitions.
    updated: list[StructureLevel] = []
    broken_highs: list[StructureLevel] = []
    broken_lows: list[StructureLevel] = []
    for level in ordered:
        if level.swing_id in crossed_ids:
            marked = replace(level, broken=True, break_index=idx)
            updated.append(marked)
            if level.direction is SwingDirection.HIGH:
                broken_highs.append(marked)
            else:
                broken_lows.append(marked)
        else:
            updated.append(level)

    choch_emitted_this_candle = False

    def _apply_group(
        group: list[StructureLevel],
        *,
        break_direction: TrendDirection,
        retired_ids: tuple[str, ...],
    ) -> None:
        nonlocal choch_emitted_this_candle
        if not group:
            return
        if break_direction is TrendDirection.BULLISH:
            rep = max(group, key=lambda level: (level.price, -level.pivot_index))
        else:
            rep = min(group, key=lambda level: (level.price, level.pivot_index))

        event_type, resulting, new_pending, is_continuation = _transition_for_break(
            track, break_direction=break_direction
        )

        # Pending reversal confirmation requires a later candle than CHOCH.
        confirms_pending = (
            track.pending_bias is not TrendDirection.RANGING
            and break_direction is track.pending_bias
            and event_type is StructureEventType.BOS
            and not is_continuation
        )
        if confirms_pending and choch_emitted_this_candle:
            # Levels already retired; skip confirming emission.
            return

        prior_bias = track.bias
        _emit_break_event(
            track,
            scope=scope,
            level=rep,
            break_index=idx,
            break_timestamp=candle.timestamp,
            break_close=close,
            break_direction=break_direction,
            event_type=event_type,
            prior_bias=prior_bias,
            resulting=resulting,
            new_pending=new_pending,
            is_continuation=is_continuation,
            retired_level_ids=retired_ids,
        )
        if event_type is StructureEventType.CHOCH:
            choch_emitted_this_candle = True

    # Deterministic order: bullish (highs) then bearish (lows).
    _apply_group(
        broken_highs,
        break_direction=TrendDirection.BULLISH,
        retired_ids=retired_ids_high,
    )
    _apply_group(
        broken_lows,
        break_direction=TrendDirection.BEARISH,
        retired_ids=retired_ids_low,
    )
    return updated


class MarketStructureDetectorV1:
    """Object-oriented wrapper around :func:`analyze_structure`."""

    def __init__(
        self,
        config: StructureDetectorConfig | None = None,
    ) -> None:
        self.config = config or StructureDetectorConfig()

    def analyze_structure(
        self,
        candles: list[Candle],
        confirmed_swings: list[DetectedSwing],
        *,
        as_of_index: int | None = None,
    ) -> StructureSnapshot:
        return analyze_structure(
            candles,
            confirmed_swings,
            as_of_index=as_of_index,
            config=self.config,
        )

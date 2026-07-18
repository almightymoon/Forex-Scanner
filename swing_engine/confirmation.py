"""Swing confirmation — rule-based (v1.3) or score-gated (v1.4)."""

from __future__ import annotations

from shared.types.models import Candle

from swing_engine.config import SwingEngineConfig
from swing_engine.confirmation_score import compute_confirmation_score, compute_score_breakdown
from swing_engine.models import InternalSwing, PivotCandidate, SwingDirection, SwingTier
from swing_engine.utils import atr_at, log_stage


def confirm_swings(
    pivots: list[PivotCandidate],
    candles: list[Candle],
    atr_series: list[float],
    config: SwingEngineConfig,
) -> list[InternalSwing]:
    n = len(candles)
    swings: list[InternalSwing] = []
    confirmed_count = 0
    score_gated = config.confirmation_score.enabled

    for i, pivot in enumerate(pivots):
        prev_opposite = _prev_opposite(pivots, i)
        prev_same = _prev_same(pivots, i)
        if score_gated:
            confirmed, conf_index, delay, reasons, meta = _evaluate_score_gated(
                pivot, candles, atr_series, config, prev_opposite, prev_same, n
            )
        else:
            confirmed, conf_index, delay, reasons = _evaluate_confirmation(
                pivot, candles, atr_series, config, prev_opposite, prev_same, n
            )
            meta = {}
        swings.append(InternalSwing(
            timestamp=pivot.pivot_timestamp,
            price=pivot.price,
            direction=pivot.direction,
            pivot_index=pivot.pivot_index,
            confirmed=confirmed,
            confirmed_timestamp=candles[conf_index].timestamp if confirmed and conf_index is not None else None,
            confirmation_index=conf_index,
            confirmation_delay=delay,
            tier=SwingTier.MINOR,
            reasoning=reasons,
            metadata={
                **pivot.metadata,
                "pivot_timestamp": pivot.pivot_timestamp.isoformat(),
                "pivot_strength": pivot.strength,
                "confirmation_reason": reasons[-1] if reasons else "none",
                "pivot_candle_index": pivot.pivot_index,
                "confirmation_candle_index": conf_index,
                **meta,
            },
        ))
        if confirmed:
            confirmed_count += 1

    log_stage("confirmation", len(pivots), len(swings), confirmed=confirmed_count)
    return swings



def _validation_end_index(
    pivot: PivotCandidate,
    min_end: int,
    conf_index: int,
    config: SwingEngineConfig,
) -> int:
    """Return the final bar on which the proposed pivot must remain intact.

    ``confirmation`` preserves the historical v2.1/v2.2 rule and validates
    the pivot through its final confirmation bar.

    ``structural_reversal`` validates through the causally detected opposite
    structural pivot. Later same-side extremes belong to the subsequent leg
    and must not retroactively erase the already established pivot.
    """
    cfg = config.confirmation

    if not cfg.validate_until_confirmation:
        return min_end

    policy = cfg.validation_boundary.strip().lower()

    if policy == "confirmation":
        return conf_index

    if policy == "structural_reversal":
        reversal_index = pivot.metadata.get(
            "structural_reversal_pivot_index"
        )

        if reversal_index is None:
            return conf_index

        try:
            boundary = int(reversal_index)
        except (TypeError, ValueError):
            return conf_index

        # Preserve the configured minimum hold while never extending beyond
        # the already calculated causal confirmation index.
        return min(
            conf_index,
            max(min_end, boundary),
        )

    raise ValueError(
        "Unsupported confirmation validation boundary: "
        f"{cfg.validation_boundary!r}"
    )


def _evaluate_score_gated(
    pivot: PivotCandidate,
    candles: list[Candle],
    atr_series: list[float],
    config: SwingEngineConfig,
    prev_opposite: PivotCandidate | None,
    prev_same: PivotCandidate | None,
    n: int,
) -> tuple[bool, int | None, int, list[str], dict]:
    cfg = config.confirmation
    idx = pivot.pivot_index
    min_end = idx + cfg.min_candles
    reasons: list[str] = []
    structural_index = pivot.metadata.get("structural_confirmation_index")
    available_index = (
        int(pivot.metadata.get("available_index", idx))
        if cfg.enforce_candidate_availability
        else idx
    )

    if min_end >= n:
        return False, None, 0, ["insufficient_bars_for_min_candles"], {}
    if config.leg.require_reversal_confirmation and structural_index is None:
        return False, None, 0, ["awaiting_structural_reversal"], {}

    conf_index = max(
        min_end,
        idx + cfg.delay_bars,
        available_index,
        int(structural_index) if structural_index is not None else idx,
    )
    if conf_index >= n:
        return False, None, 0, ["insufficient_bars_for_delay"], {}

    validation_end = _validation_end_index(
        pivot,
        min_end,
        conf_index,
        config,
    )
    for check_index in range(idx + 1, validation_end + 1):
        bar = candles[check_index]
        if pivot.direction == SwingDirection.HIGH and bar.high > pivot.price:
            return False, None, 0, [f"high_violated_at_bar_{check_index}"], {}
        if pivot.direction == SwingDirection.LOW and bar.low < pivot.price:
            return False, None, 0, [f"low_violated_at_bar_{check_index}"], {}

    delay = conf_index - idx
    if structural_index is not None:
        reasons.append(f"structural_reversal_confirmed_at_bar_{structural_index}")
    score, factors, checks = compute_confirmation_score(
        pivot, candles, atr_series, config,
        prev_opposite=prev_opposite, prev_same=prev_same,
        conf_index=conf_index, delay=delay,
    )
    threshold = config.confirmation_score.threshold
    confirmed = score >= threshold
    reasons.append(f"confirmation_score={score:.1f} threshold={threshold}")
    if confirmed:
        reasons.append(f"confirmed_at_bar_{conf_index}")
    else:
        reasons.append("below_confirmation_threshold")

    meta = {
        "confirmation_score": score,
        "confirmation_threshold": threshold,
        "confirmation_factors": factors,
        "confirmation_checks": checks,
        "confirmation_breakdown": compute_score_breakdown(
            factors, config.confirmation_score.weights, score
        ),
    }
    return confirmed, conf_index if confirmed else None, delay if confirmed else 0, reasons, meta


def _prev_opposite(pivots: list[PivotCandidate], index: int) -> PivotCandidate | None:
    direction = pivots[index].direction
    for j in range(index - 1, -1, -1):
        if pivots[j].direction != direction:
            return pivots[j]
    return None


def _prev_same(pivots: list[PivotCandidate], index: int) -> PivotCandidate | None:
    direction = pivots[index].direction
    for j in range(index - 1, -1, -1):
        if pivots[j].direction == direction:
            return pivots[j]
    return None


def _evaluate_confirmation(
    pivot: PivotCandidate,
    candles: list[Candle],
    atr_series: list[float],
    config: SwingEngineConfig,
    prev_opposite: PivotCandidate | None,
    prev_same: PivotCandidate | None,
    n: int,
) -> tuple[bool, int | None, int, list[str]]:
    cfg = config.confirmation
    reasons: list[str] = []
    idx = pivot.pivot_index
    min_end = idx + cfg.min_candles
    structural_index = pivot.metadata.get("structural_confirmation_index")
    available_index = (
        int(pivot.metadata.get("available_index", idx))
        if cfg.enforce_candidate_availability
        else idx
    )

    if min_end >= n:
        return False, None, 0, ["insufficient_bars_for_min_candles"]
    if config.leg.require_reversal_confirmation and structural_index is None:
        return False, None, 0, ["awaiting_structural_reversal"]

    conf_index = max(
        min_end,
        idx + cfg.delay_bars,
        available_index,
        int(structural_index) if structural_index is not None else idx,
    )
    if conf_index >= n:
        return False, None, 0, ["insufficient_bars_for_delay"]

    validation_end = _validation_end_index(
        pivot,
        min_end,
        conf_index,
        config,
    )
    for check_index in range(idx + 1, validation_end + 1):
        bar = candles[check_index]
        if pivot.direction == SwingDirection.HIGH and bar.high > pivot.price:
            return False, None, 0, [f"high_violated_at_bar_{check_index}"]
        if pivot.direction == SwingDirection.LOW and bar.low < pivot.price:
            return False, None, 0, [f"low_violated_at_bar_{check_index}"]

    held_bars = validation_end - idx
    reasons.append(f"held_for_{held_bars}_candles")
    if structural_index is not None:
        reasons.append(f"structural_reversal_confirmed_at_bar_{structural_index}")
    atr = atr_at(idx, atr_series, candles)

    if cfg.displacement_atr_min > 0:
        disp_end = min(n, idx + cfg.displacement_bars + 1)
        seg = candles[idx + 1 : disp_end]
        if seg:
            if pivot.direction == SwingDirection.HIGH:
                disp = pivot.price - min(c.low for c in seg)
            else:
                disp = max(c.high for c in seg) - pivot.price
            if disp < cfg.displacement_atr_min * atr:
                return False, None, 0, ["insufficient_displacement"]
            reasons.append(f"displacement_atr={disp / atr:.2f}")

    if cfg.require_structure_break and prev_opposite:
        if pivot.direction == SwingDirection.HIGH and pivot.price <= prev_opposite.price:
            return False, None, 0, ["structure_break_required_but_not_met"]
        if pivot.direction == SwingDirection.LOW and pivot.price >= prev_opposite.price:
            return False, None, 0, ["structure_break_required_but_not_met"]
        reasons.append("structure_break_confirmed")

    if cfg.break_internal_structure and prev_same and prev_opposite:
        mid = (prev_same.price + prev_opposite.price) / 2
        if pivot.direction == SwingDirection.HIGH and pivot.price <= mid:
            return False, None, 0, ["internal_structure_not_broken"]
        if pivot.direction == SwingDirection.LOW and pivot.price >= mid:
            return False, None, 0, ["internal_structure_not_broken"]
        reasons.append("internal_structure_broken")

    if cfg.required_retracement_atr > 0 and prev_opposite:
        retrace = abs(pivot.price - prev_opposite.price) / atr if atr > 0 else 0
        if retrace < cfg.required_retracement_atr:
            return False, None, 0, ["insufficient_retracement"]
        reasons.append(f"retracement_atr={retrace:.2f}")

    return True, conf_index, conf_index - idx, reasons + [f"confirmed_at_bar_{conf_index}"]

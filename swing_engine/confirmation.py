"""Swing confirmation — no repaint, multiple configurable methods."""

from __future__ import annotations

from shared.types.models import Candle

from swing_engine.config import SwingEngineConfig
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

    for i, pivot in enumerate(pivots):
        prev_opposite = _prev_opposite(pivots, i)
        prev_same = _prev_same(pivots, i)
        confirmed, conf_index, delay, reasons = _evaluate_confirmation(
            pivot, candles, atr_series, config, prev_opposite, prev_same, n
        )
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
                "pivot_timestamp": pivot.pivot_timestamp.isoformat(),
                "pivot_strength": pivot.strength,
                "confirmation_reason": reasons[-1] if reasons else "none",
                "pivot_candle_index": pivot.pivot_index,
                "confirmation_candle_index": conf_index,
            },
        ))
        if confirmed:
            confirmed_count += 1

    log_stage("confirmation", len(pivots), len(swings), confirmed=confirmed_count)
    return swings


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

    if min_end >= n:
        return False, None, 0, ["insufficient_bars_for_min_candles"]

    for j in range(1, cfg.min_candles + 1):
        bar = candles[idx + j]
        if pivot.direction == SwingDirection.HIGH and bar.high > pivot.price:
            return False, None, 0, [f"high_violated_at_bar_{idx + j}"]
        if pivot.direction == SwingDirection.LOW and bar.low < pivot.price:
            return False, None, 0, [f"low_violated_at_bar_{idx + j}"]

    reasons.append(f"held_for_{cfg.min_candles}_candles")

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

    conf_index = max(min_end, idx + cfg.delay_bars)
    if conf_index >= n:
        return False, None, 0, ["insufficient_bars_for_delay"]

    return True, conf_index, conf_index - idx, reasons + [f"confirmed_at_bar_{conf_index}"]

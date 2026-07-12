"""Swing confirmation — no repaint."""

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
        confirmed, conf_index, delay, reasons = _evaluate_confirmation(
            pivot, candles, atr_series, config, prev_opposite, n
        )
        swings.append(InternalSwing(
            timestamp=pivot.pivot_timestamp,
            price=pivot.price,
            direction=pivot.direction,
            pivot_index=pivot.pivot_index,
            confirmed=confirmed,
            confirmed_timestamp=candles[conf_index].timestamp if confirmed and conf_index else None,
            confirmation_index=conf_index,
            confirmation_delay=delay,
            tier=SwingTier.MINOR,
            reasoning=reasons,
            metadata={"pivot_timestamp": pivot.pivot_timestamp.isoformat()},
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


def _evaluate_confirmation(
    pivot: PivotCandidate,
    candles: list[Candle],
    atr_series: list[float],
    config: SwingEngineConfig,
    prev_opposite: PivotCandidate | None,
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

    if cfg.require_structure_break and prev_opposite:
        if pivot.direction == SwingDirection.HIGH and pivot.price <= prev_opposite.price:
            return False, None, 0, ["structure_break_required_but_not_met"]
        if pivot.direction == SwingDirection.LOW and pivot.price >= prev_opposite.price:
            return False, None, 0, ["structure_break_required_but_not_met"]
        reasons.append("structure_break_confirmed")

    if cfg.required_retracement_atr > 0 and prev_opposite:
        atr = atr_at(idx, atr_series, candles)
        retrace = abs(pivot.price - prev_opposite.price) / atr if atr > 0 else 0
        if retrace < cfg.required_retracement_atr:
            return False, None, 0, ["insufficient_retracement"]
        reasons.append(f"retracement_atr={retrace:.2f}")

    conf_index = max(min_end, idx + cfg.delay_bars)
    if conf_index >= n:
        return False, None, 0, ["insufficient_bars_for_delay"]

    return True, conf_index, conf_index - idx, reasons + [f"confirmed_at_bar_{conf_index}"]

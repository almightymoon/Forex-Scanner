"""Swing confirmation — no repaint of confirmed swings."""

from __future__ import annotations

from shared.types.models import Candle

from scanner.swing_detection.models import PivotCandidate, Swing, SwingClassification, SwingDirection
from scanner.swing_detection.utils import SwingDetectionConfig, atr_at, log_stage


def confirm_swings(
    pivots: list[PivotCandidate],
    candles: list[Candle],
    atr_series: list[float],
    config: SwingDetectionConfig,
) -> list[Swing]:
    """
    Apply confirmation rules. Confirmed swings are immutable — criteria depend only
    on bars from pivot_index through confirmation_index (never future data).
    """
    cfg = config.confirmation
    n = len(candles)
    swings: list[Swing] = []
    confirmed_count = 0

    for i, pivot in enumerate(pivots):
        prev_opposite = _prev_opposite(pivots, i)
        confirmed, conf_index, delay, reasons = _evaluate_confirmation(
            pivot, candles, atr_series, config, prev_opposite, n
        )

        swing = Swing(
            timestamp=pivot.pivot_timestamp,
            price=pivot.price,
            direction=pivot.direction,
            pivot_index=pivot.pivot_index,
            confirmed=confirmed,
            confirmed_timestamp=candles[conf_index].timestamp if confirmed and conf_index is not None else None,
            confirmation_index=conf_index,
            confirmation_delay=delay,
            classification=SwingClassification.MINOR,
            reasoning=reasons,
            metadata={"pivot_timestamp": pivot.pivot_timestamp.isoformat()},
        )
        swings.append(swing)
        if confirmed:
            confirmed_count += 1

    log_stage(
        "confirmation",
        len(pivots),
        len(swings),
        confirmed=confirmed_count,
        unconfirmed=len(swings) - confirmed_count,
    )
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
    config: SwingDetectionConfig,
    prev_opposite: PivotCandidate | None,
    n: int,
) -> tuple[bool, int | None, int, list[str]]:
    cfg = config.confirmation
    reasons: list[str] = []
    idx = pivot.pivot_index
    min_end = idx + cfg.min_candles
    delay_end = idx + cfg.delay_bars

    if min_end >= n:
        reasons.append("insufficient_bars_for_min_candles")
        return False, None, 0, reasons

    # Hold test: level not violated during confirmation window
    hold_end = idx + cfg.min_candles
    for j in range(1, cfg.min_candles + 1):
        bar = candles[idx + j]
        if pivot.direction == SwingDirection.HIGH and bar.high > pivot.price:
            reasons.append(f"high_violated_at_bar_{idx + j}")
            return False, None, 0, reasons
        if pivot.direction == SwingDirection.LOW and bar.low < pivot.price:
            reasons.append(f"low_violated_at_bar_{idx + j}")
            return False, None, 0, reasons

    reasons.append(f"held_for_{cfg.min_candles}_candles")

    # Optional structure break
    if cfg.require_structure_break and prev_opposite:
        if pivot.direction == SwingDirection.HIGH and pivot.price <= prev_opposite.price:
            reasons.append("structure_break_required_but_not_met")
            return False, None, 0, reasons
        if pivot.direction == SwingDirection.LOW and pivot.price >= prev_opposite.price:
            reasons.append("structure_break_required_but_not_met")
            return False, None, 0, reasons
        reasons.append("structure_break_confirmed")

    # Optional retracement from prior leg
    if cfg.required_retracement_atr > 0 and prev_opposite:
        atr = atr_at(idx, atr_series, candles)
        leg = abs(pivot.price - prev_opposite.price)
        retrace = leg / atr if atr > 0 else 0
        if retrace < cfg.required_retracement_atr:
            reasons.append("insufficient_retracement")
            return False, None, 0, reasons
        reasons.append(f"retracement_atr={retrace:.2f}")

    conf_index = max(min_end, delay_end)
    if conf_index >= n:
        reasons.append("insufficient_bars_for_delay")
        return False, None, 0, reasons

    delay = conf_index - idx
    reasons.append(f"confirmed_at_bar_{conf_index}")
    return True, conf_index, delay, reasons

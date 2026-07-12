"""Swing scoring, scope classification, and confidence."""

from __future__ import annotations

import logging

from shared.types.models import Candle

from scanner.swing_detection.strength import calculate_strength, score_all_swings
from scanner.swing_detection.utils import SwingDetectionConfig, atr_at, log_stage
from swing_engine.models import DetectedSwing, SwingDirection, SwingScope, SwingTier

logger = logging.getLogger("fxnav.swing_engine.scoring")


def classify_scope(
    swing: DetectedSwing,
    prev_same: DetectedSwing | None,
    prev_opposite: DetectedSwing | None,
    candles: list[Candle],
    config: SwingDetectionConfig,
) -> SwingScope:
    """Score-based internal/external classification — no hardcoded decisions."""
    if not prev_same and not prev_opposite:
        return SwingScope.NEUTRAL

    score = 0.0
    reasons: list[str] = []

    if prev_same:
        if swing.direction == SwingDirection.HIGH and swing.price > prev_same.price:
            score += config.classification.major_min_atr_multiple
            reasons.append("broke_prior_high")
        elif swing.direction == SwingDirection.LOW and swing.price < prev_same.price:
            score += config.classification.major_min_atr_multiple
            reasons.append("broke_prior_low")

    if prev_opposite and prev_same:
        range_size = abs(prev_same.price - prev_opposite.price)
        if range_size > 0:
            mid = min(prev_same.price, prev_opposite.price) + range_size * 0.5
            if swing.direction == SwingDirection.HIGH and swing.price < mid:
                score -= 0.5
                reasons.append("below_range_mid")
            elif swing.direction == SwingDirection.LOW and swing.price > mid:
                score -= 0.5
                reasons.append("above_range_mid")

    threshold = config.classification.external_score_threshold * 0.5
    if score >= threshold:
        scope = SwingScope.EXTERNAL
    elif score <= config.classification.internal_score_threshold:
        scope = SwingScope.INTERNAL
    else:
        scope = SwingScope.NEUTRAL

    swing.metadata["scope_score"] = round(score, 3)
    swing.metadata["scope_reasons"] = reasons
    return scope


def compute_confidence(swing: DetectedSwing, config: SwingDetectionConfig) -> float:
    """Derive 0–1 confidence from confirmation quality and strength."""
    cc = config.confidence
    base = swing.score / 100.0
    if swing.confirmed:
        base = min(1.0, base + cc.confirmed_bonus)
    else:
        base *= cc.unconfirmed_penalty
    if swing.tier == SwingTier.MAJOR:
        base = min(1.0, base * cc.major_multiplier)
    delay_penalty = min(0.2, swing.confirmation_delay * cc.delay_penalty_per_bar)
    return round(max(0.0, min(1.0, base - delay_penalty)), 4)


def classify_tier(swing: DetectedSwing, leg_atr: float, config: SwingDetectionConfig) -> SwingTier:
    """Major/minor from configurable ATR and strength thresholds."""
    is_major = (
        leg_atr >= config.classification.major_min_atr_multiple
        and swing.strength >= config.classification.major_min_strength
    )
    return SwingTier.MAJOR if is_major else SwingTier.MINOR


def score_and_classify(
    internal_swings: list,
    candles: list[Candle],
    atr_series: list[float],
    config: SwingDetectionConfig,
) -> list[DetectedSwing]:
    """Convert internal swings to DetectedSwing with scope, tier, confidence."""
    scored_internal = score_all_swings(internal_swings, candles, atr_series, config)

    detected: list[DetectedSwing] = []
    last_by_dir: dict[SwingDirection, DetectedSwing | None] = {
        SwingDirection.HIGH: None,
        SwingDirection.LOW: None,
    }

    for i, s in enumerate(scored_internal):
        prev_internal = scored_internal[i - 1] if i > 0 else None
        atr = atr_at(s.pivot_index, atr_series, candles)
        leg = (
            abs(s.price - prev_internal.price)
            if prev_internal and prev_internal.direction != s.direction
            else atr
        )
        leg_atr = leg / atr if atr > 0 else 0.0

        ds = DetectedSwing(
            timestamp=s.timestamp,
            price=s.price,
            direction=SwingDirection(s.direction.value),
            tier=SwingTier.MINOR,
            scope=SwingScope.NEUTRAL,
            pivot_index=s.pivot_index,
            confirmed=s.confirmed,
            confirmed_timestamp=s.confirmed_timestamp,
            confirmation_index=s.confirmation_index,
            confirmation_delay=s.confirmation_delay,
            strength=s.strength,
            score=s.score,
            reasoning=list(s.reasoning),
            metadata=dict(s.metadata),
        )
        ds.tier = classify_tier(ds, leg_atr, config)
        opp = SwingDirection.LOW if ds.direction == SwingDirection.HIGH else SwingDirection.HIGH
        ds.scope = classify_scope(ds, last_by_dir[ds.direction], last_by_dir[opp], candles, config)
        ds.confidence = compute_confidence(ds, config)
        ds.metadata["leg_atr"] = round(leg_atr, 3)
        detected.append(ds)
        last_by_dir[ds.direction] = ds

    log_stage(
        "scoring",
        len(internal_swings),
        len(detected),
        major=sum(1 for d in detected if d.tier == SwingTier.MAJOR),
        external=sum(1 for d in detected if d.scope == SwingScope.EXTERNAL),
    )
    return detected

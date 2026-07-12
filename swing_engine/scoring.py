"""Final scoring — tier, scope, confidence."""

from __future__ import annotations

from shared.types.models import Candle

from swing_engine.config import SwingEngineConfig
from swing_engine.models import DetectedSwing, InternalSwing, SwingDirection, SwingScope, SwingTier
from swing_engine.strength import score_all_swings
from swing_engine.utils import atr_at, log_stage


def classify_scope(
    swing: DetectedSwing,
    prev_same: DetectedSwing | None,
    prev_opposite: DetectedSwing | None,
    config: SwingEngineConfig,
) -> SwingScope:
    score = 0.0
    if prev_same:
        if swing.direction == SwingDirection.HIGH and swing.price > prev_same.price:
            score += config.classification.major_min_atr_multiple
        elif swing.direction == SwingDirection.LOW and swing.price < prev_same.price:
            score += config.classification.major_min_atr_multiple
    if prev_opposite and prev_same:
        rng = abs(prev_same.price - prev_opposite.price)
        if rng > 0:
            mid = min(prev_same.price, prev_opposite.price) + rng * 0.5
            if swing.direction == SwingDirection.HIGH and swing.price < mid:
                score -= 0.5
            elif swing.direction == SwingDirection.LOW and swing.price > mid:
                score -= 0.5

    threshold = config.classification.external_score_threshold * 0.5
    if score >= threshold:
        return SwingScope.EXTERNAL
    if score <= config.classification.internal_score_threshold:
        return SwingScope.INTERNAL
    return SwingScope.NEUTRAL


def compute_confidence(swing: DetectedSwing, config: SwingEngineConfig) -> float:
    cc = config.confidence
    base = swing.score / 100.0
    if swing.confirmed:
        base = min(1.0, base + cc.confirmed_bonus)
    else:
        base *= cc.unconfirmed_penalty
    if swing.tier == SwingTier.MAJOR:
        base = min(1.0, base * cc.major_multiplier)
    return round(max(0.0, min(1.0, base - min(0.2, swing.confirmation_delay * cc.delay_penalty_per_bar))), 4)


def score_and_classify(
    internal: list[InternalSwing],
    candles: list[Candle],
    atr_series: list[float],
    config: SwingEngineConfig,
) -> list[DetectedSwing]:
    scored = score_all_swings(internal, candles, atr_series, config)
    detected: list[DetectedSwing] = []
    last: dict[SwingDirection, DetectedSwing | None] = {SwingDirection.HIGH: None, SwingDirection.LOW: None}

    for i, s in enumerate(scored):
        prev = scored[i - 1] if i > 0 else None
        atr = atr_at(s.pivot_index, atr_series, candles)
        leg = abs(s.price - prev.price) if prev and prev.direction != s.direction else atr
        leg_atr = leg / atr if atr > 0 else 0.0

        ds = DetectedSwing(
            timestamp=s.timestamp, price=s.price, direction=s.direction,
            tier=SwingTier.MINOR, scope=SwingScope.NEUTRAL, pivot_index=s.pivot_index,
            confirmed=s.confirmed, confirmed_timestamp=s.confirmed_timestamp,
            confirmation_index=s.confirmation_index, confirmation_delay=s.confirmation_delay,
            strength=s.strength, score=s.score, reasoning=list(s.reasoning), metadata=dict(s.metadata),
        )
        if leg_atr >= config.classification.major_min_atr_multiple and s.strength >= config.classification.major_min_strength:
            ds.tier = SwingTier.MAJOR
        opp = SwingDirection.LOW if ds.direction == SwingDirection.HIGH else SwingDirection.HIGH
        ds.scope = classify_scope(ds, last[ds.direction], last[opp], config)
        ds.confidence = compute_confidence(ds, config)
        ds.metadata["leg_atr"] = round(leg_atr, 3)
        detected.append(ds)
        last[ds.direction] = ds

    log_stage("scoring", len(internal), len(detected))
    return detected

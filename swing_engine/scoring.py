"""Final scoring — tier, scope, confidence with protected structure levels."""

from __future__ import annotations

from shared.types.models import Candle

from swing_engine.config import SwingEngineConfig
from swing_engine.explain import build_swing_explanation
from swing_engine.models import DetectedSwing, InternalSwing, SwingDirection, SwingScope, SwingTier
from swing_engine.quality import compute_quality_score
from swing_engine.strength import score_all_swings
from swing_engine.utils import atr_at, log_stage


def classify_scope(
    swing: DetectedSwing,
    prev_same: DetectedSwing | None,
    prev_opposite: DetectedSwing | None,
    protected_high: float | None,
    protected_low: float | None,
    config: SwingEngineConfig,
) -> SwingScope:
    clf = config.classification
    score = 0.0

    if prev_same:
        if swing.direction == SwingDirection.HIGH and swing.price > prev_same.price:
            score += clf.external_score_threshold
        elif swing.direction == SwingDirection.LOW and swing.price < prev_same.price:
            score += clf.external_score_threshold

    if prev_opposite and prev_same:
        rng = abs(prev_same.price - prev_opposite.price)
        if rng > 0:
            mid = min(prev_same.price, prev_opposite.price) + rng * 0.5
            if swing.direction == SwingDirection.HIGH and swing.price < mid:
                score -= 0.5
            elif swing.direction == SwingDirection.LOW and swing.price > mid:
                score -= 0.5

    if protected_high is not None and protected_low is not None:
        dealing_mid = (protected_high + protected_low) / 2
        if swing.direction == SwingDirection.HIGH and swing.price < dealing_mid:
            score -= 0.35
        elif swing.direction == SwingDirection.LOW and swing.price > dealing_mid:
            score -= 0.35
        if swing.direction == SwingDirection.HIGH and swing.price > protected_high:
            score += 0.25
        elif swing.direction == SwingDirection.LOW and swing.price < protected_low:
            score += 0.25

    threshold = clf.external_score_threshold * 0.5
    if score >= threshold:
        return SwingScope.EXTERNAL
    if score <= clf.internal_score_threshold:
        return SwingScope.INTERNAL
    return SwingScope.NEUTRAL


def classify_tier(
    swing: DetectedSwing,
    leg_atr: float,
    reaction_atr: float,
    duration: int,
    config: SwingEngineConfig,
) -> SwingTier:
    clf = config.classification
    tw = clf.tier_weights

    tier_score = (
        min(1.0, leg_atr / clf.major_min_atr_multiple) * tw.leg_atr * 100
        + (swing.strength / 5.0) * tw.strength * 100
        + min(1.0, reaction_atr / 1.5) * tw.reaction * 100
        + (1.0 if swing.confirmed else 0.4) * tw.confirmation * 100
        + min(1.0, duration / 20.0) * tw.duration * 100
    )

    swing.metadata["tier_score"] = round(tier_score, 2)

    if leg_atr >= clf.major_min_atr_multiple and swing.strength >= clf.major_min_strength:
        return SwingTier.MAJOR
    if leg_atr <= clf.minor_max_atr_multiple and swing.strength < clf.major_min_strength:
        return SwingTier.MINOR
    return SwingTier.MAJOR if tier_score >= 55 else SwingTier.MINOR


def compute_confidence(swing: DetectedSwing, config: SwingEngineConfig) -> float:
    cc = config.confidence
    base = swing.normalized_score / 100.0
    if swing.confirmed:
        base = min(1.0, base + cc.confirmed_bonus)
    else:
        base *= cc.unconfirmed_penalty
    if swing.tier == SwingTier.MAJOR:
        base = min(1.0, base * cc.major_multiplier)
    return round(max(0.0, min(1.0, base - min(0.2, swing.confirmation_delay * cc.delay_penalty_per_bar))), 4)


def _protected_levels(
    detected: list[DetectedSwing],
    index: int,
    lookback: int,
) -> tuple[float | None, float | None]:
    prior = detected[:index]
    highs = [s.price for s in prior if s.direction == SwingDirection.HIGH][-lookback:]
    lows = [s.price for s in prior if s.direction == SwingDirection.LOW][-lookback:]
    return (max(highs) if highs else None, min(lows) if lows else None)


def score_and_classify(
    internal: list[InternalSwing],
    candles: list[Candle],
    atr_series: list[float],
    config: SwingEngineConfig,
) -> list[DetectedSwing]:
    scored = score_all_swings(internal, candles, atr_series, config)
    detected: list[DetectedSwing] = []
    last: dict[SwingDirection, DetectedSwing | None] = {SwingDirection.HIGH: None, SwingDirection.LOW: None}
    lookback = config.classification.protected_lookback_swings

    for i, s in enumerate(scored):
        prev = scored[i - 1] if i > 0 else None
        atr = atr_at(s.pivot_index, atr_series, candles)
        leg = abs(s.price - prev.price) if prev and prev.direction != s.direction else atr
        leg_atr = leg / atr if atr > 0 else 0.0
        reaction = abs(s.price - candles[min(s.pivot_index + 1, len(candles) - 1)].close)
        reaction_atr = reaction / atr if atr > 0 else 0.0
        duration = s.pivot_index - prev.pivot_index if prev else 1

        ds = DetectedSwing(
            timestamp=s.timestamp, price=s.price, direction=s.direction,
            tier=SwingTier.MINOR, scope=SwingScope.NEUTRAL, pivot_index=s.pivot_index,
            confirmed=s.confirmed, confirmed_timestamp=s.confirmed_timestamp,
            confirmation_index=s.confirmation_index, confirmation_delay=s.confirmation_delay,
            strength=s.strength, score=s.score, normalized_score=s.normalized_score,
            reasoning=list(s.reasoning), metadata=dict(s.metadata),
        )
        ds.tier = classify_tier(ds, leg_atr, reaction_atr, duration, config)
        opp = SwingDirection.LOW if ds.direction == SwingDirection.HIGH else SwingDirection.HIGH
        prev_same, prev_opp = last[ds.direction], last[opp]
        prot_hi, prot_lo = _protected_levels(detected, i, lookback)
        ds.scope = classify_scope(ds, prev_same, prev_opp, prot_hi, prot_lo, config)
        ds.confidence = compute_confidence(ds, config)
        ds.metadata["leg_atr"] = round(leg_atr, 3)
        ds.quality_score, ds.quality_factors = compute_quality_score(
            ds, prev_same, prev_opp, candles, atr_series, config
        )
        ds.explanation = build_swing_explanation(ds, config)
        detected.append(ds)
        last[ds.direction] = ds

    log_stage("scoring", len(internal), len(detected))
    return detected

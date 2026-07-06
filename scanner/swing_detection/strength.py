"""Swing strength scoring (1–5) with explainable reasoning."""

from __future__ import annotations

from shared.types.models import Candle

from scanner.swing_detection.models import Swing, SwingClassification, SwingDirection
from scanner.swing_detection.utils import SwingDetectionConfig, atr_at, log_stage


def calculate_strength(
    swing: Swing,
    candles: list[Candle],
    atr_series: list[float],
    prev_opposite: Swing | None,
    config: SwingDetectionConfig,
) -> Swing:
    """Compute strength 1–5, raw score, and reasoning."""
    weights = config.strength.weights
    atr = atr_at(swing.pivot_index, atr_series, candles)

    leg_size = abs(swing.price - prev_opposite.price) if prev_opposite else atr
    leg_atr = leg_size / atr if atr > 0 else 0.0

    reaction = _reaction_size(candles, swing)
    reaction_atr = reaction / atr if atr > 0 else 0.0

    duration = swing.pivot_index - prev_opposite.pivot_index if prev_opposite else 1
    duration_score = min(1.0, duration / 20.0)

    volume_score = _volume_score(candles, swing)

    leg_component = min(1.0, leg_atr / 2.5) * 100
    atr_component = min(1.0, leg_atr / 2.0) * 100
    reaction_component = min(1.0, reaction_atr / 1.5) * 100
    duration_component = duration_score * 100
    volume_component = volume_score * 100

    score = (
        leg_component * weights.get("leg_size", 0.25)
        + atr_component * weights.get("atr_multiple", 0.25)
        + reaction_component * weights.get("reaction_size", 0.20)
        + duration_component * weights.get("duration", 0.15)
        + volume_component * weights.get("volume", 0.15)
    )

    if not swing.confirmed:
        score *= 0.85

    strength = _score_to_level(score, config)
    reasoning = [
        f"leg_atr={leg_atr:.2f}",
        f"reaction_atr={reaction_atr:.2f}",
        f"duration_bars={duration}",
        f"volume_score={volume_score:.2f}",
        f"composite_score={score:.1f}",
        f"strength_level={strength}",
    ]

    swing.score = round(score, 2)
    swing.strength = strength
    swing.reasoning = list(swing.reasoning) + reasoning
    swing.metadata["strength_components"] = {
        "leg": round(leg_component, 2),
        "atr": round(atr_component, 2),
        "reaction": round(reaction_component, 2),
        "duration": round(duration_component, 2),
        "volume": round(volume_component, 2),
    }
    return swing


def score_all_swings(
    swings: list[Swing],
    candles: list[Candle],
    atr_series: list[float],
    config: SwingDetectionConfig,
) -> list[Swing]:
    """Score each swing against its previous opposite swing."""
    scored: list[Swing] = []
    last_opposite: dict[SwingDirection, Swing | None] = {
        SwingDirection.HIGH: None,
        SwingDirection.LOW: None,
    }

    for swing in swings:
        opp_dir = SwingDirection.LOW if swing.direction == SwingDirection.HIGH else SwingDirection.HIGH
        prev = last_opposite[opp_dir]
        scored_swing = calculate_strength(swing, candles, atr_series, prev, config)
        scored.append(scored_swing)
        last_opposite[swing.direction] = scored_swing

    log_stage("strength", len(swings), len(scored), avg_strength=_avg_strength(scored))
    return scored


def classify_swings(
    swings: list[Swing],
    candles: list[Candle],
    atr_series: list[float],
    config: SwingDetectionConfig,
) -> list[Swing]:
    """Major/minor classification from config thresholds."""
    cc = config.classification
    major = 0
    minor = 0

    for i, swing in enumerate(swings):
        prev = swings[i - 1] if i > 0 else None
        atr = atr_at(swing.pivot_index, atr_series, candles)
        leg = abs(swing.price - prev.price) if prev and prev.direction != swing.direction else atr
        leg_atr = leg / atr if atr > 0 else 0

        is_major = leg_atr >= cc.major_min_atr_multiple and swing.strength >= cc.major_min_strength
        swing.classification = SwingClassification.MAJOR if is_major else SwingClassification.MINOR
        swing.metadata["leg_atr"] = round(leg_atr, 3)
        if is_major:
            major += 1
        else:
            minor += 1

    log_stage("classification", len(swings), len(swings), major=major, minor=minor)
    return swings


def _reaction_size(candles: list[Candle], swing: Swing) -> float:
    end = min(len(candles), swing.pivot_index + 4)
    if swing.pivot_index + 1 >= end:
        return 0.0
    segment = candles[swing.pivot_index + 1 : end]
    if swing.direction == SwingDirection.HIGH:
        return swing.price - min(c.low for c in segment)
    return max(c.high for c in segment) - swing.price


def _volume_score(candles: list[Candle], swing: Swing) -> float:
    idx = swing.pivot_index
    if idx < 5 or not candles[idx].volume:
        return 0.5
    window = [candles[j].volume for j in range(max(0, idx - 10), idx) if candles[j].volume]
    if not window:
        return 0.5
    avg = sum(window) / len(window)
    return min(1.0, candles[idx].volume / avg) if avg > 0 else 0.5


def _score_to_level(score: float, config: SwingDetectionConfig) -> int:
    thresholds = config.strength.level_thresholds
    for level, threshold in enumerate(thresholds, start=1):
        if score < threshold:
            return level
    return len(thresholds) + 1


def _avg_strength(swings: list[Swing]) -> float:
    if not swings:
        return 0.0
    return sum(s.strength for s in swings) / len(swings)

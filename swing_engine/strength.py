"""Internal strength scoring (1–5) before final classification."""

from __future__ import annotations

from shared.types.models import Candle

from swing_engine.config import SwingEngineConfig
from swing_engine.models import InternalSwing, SwingDirection, SwingTier
from swing_engine.utils import atr_at, log_stage


def calculate_strength(
    swing: InternalSwing,
    candles: list[Candle],
    atr_series: list[float],
    prev_opposite: InternalSwing | None,
    config: SwingEngineConfig,
) -> InternalSwing:
    weights = config.strength.weights
    atr = atr_at(swing.pivot_index, atr_series, candles)
    leg_size = abs(swing.price - prev_opposite.price) if prev_opposite else atr
    leg_atr = leg_size / atr if atr > 0 else 0.0
    reaction = _reaction_size(candles, swing)
    reaction_atr = reaction / atr if atr > 0 else 0.0
    duration = swing.pivot_index - prev_opposite.pivot_index if prev_opposite else 1
    duration_score = min(1.0, duration / 20.0)
    volume_score = _volume_score(candles, swing)

    leg_c = min(1.0, leg_atr / 2.5) * 100
    atr_c = min(1.0, leg_atr / 2.0) * 100
    react_c = min(1.0, reaction_atr / 1.5) * 100
    dur_c = duration_score * 100
    vol_c = volume_score * 100

    score = (
        leg_c * weights.get("leg_size", 0.25)
        + atr_c * weights.get("atr_multiple", 0.25)
        + react_c * weights.get("reaction_size", 0.20)
        + dur_c * weights.get("duration", 0.15)
        + vol_c * weights.get("volume", 0.15)
    )
    if not swing.confirmed:
        score *= 0.85

    swing.score = round(score, 2)
    swing.strength = _score_to_level(score, config)
    swing.reasoning.extend([
        f"leg_atr={leg_atr:.2f}", f"composite_score={score:.1f}", f"strength={swing.strength}",
    ])
    swing.metadata["strength_components"] = {
        "leg": round(leg_c, 2), "atr": round(atr_c, 2), "reaction": round(react_c, 2),
    }
    return swing


def score_all_swings(
    swings: list[InternalSwing],
    candles: list[Candle],
    atr_series: list[float],
    config: SwingEngineConfig,
) -> list[InternalSwing]:
    scored: list[InternalSwing] = []
    last_opp: dict[SwingDirection, InternalSwing | None] = {SwingDirection.HIGH: None, SwingDirection.LOW: None}
    for swing in swings:
        opp = SwingDirection.LOW if swing.direction == SwingDirection.HIGH else SwingDirection.HIGH
        scored.append(calculate_strength(swing, candles, atr_series, last_opp[opp], config))
        last_opp[swing.direction] = scored[-1]
    log_stage("strength", len(swings), len(scored))
    return scored


def _reaction_size(candles: list[Candle], swing: InternalSwing) -> float:
    end = min(len(candles), swing.pivot_index + 4)
    if swing.pivot_index + 1 >= end:
        return 0.0
    seg = candles[swing.pivot_index + 1 : end]
    if swing.direction == SwingDirection.HIGH:
        return swing.price - min(c.low for c in seg)
    return max(c.high for c in seg) - swing.price


def _volume_score(candles: list[Candle], swing: InternalSwing) -> float:
    idx = swing.pivot_index
    if idx < 5 or not candles[idx].volume:
        return 0.5
    window = [candles[j].volume for j in range(max(0, idx - 10), idx) if candles[j].volume]
    return min(1.0, candles[idx].volume / (sum(window) / len(window))) if window else 0.5


def _score_to_level(score: float, config: SwingEngineConfig) -> int:
    for level, threshold in enumerate(config.strength.level_thresholds, start=1):
        if score < threshold:
            return level
    return len(config.strength.level_thresholds) + 1

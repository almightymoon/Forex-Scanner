"""Internal strength scoring (1–5) with raw and normalized scores."""

from __future__ import annotations

from shared.types.models import Candle

from swing_engine.config import SwingEngineConfig
from swing_engine.models import InternalSwing, SwingDirection
from swing_engine.utils import atr_at, log_stage


def calculate_strength(
    swing: InternalSwing,
    candles: list[Candle],
    atr_series: list[float],
    prev_opposite: InternalSwing | None,
    config: SwingEngineConfig,
) -> InternalSwing:
    sc = config.strength
    weights = sc.weights
    atr = atr_at(swing.pivot_index, atr_series, candles)
    leg_size = abs(swing.price - prev_opposite.price) if prev_opposite else atr
    leg_atr = leg_size / atr if atr > 0 else 0.0
    reaction = _reaction_size(candles, swing, sc.reaction_bars)
    reaction_atr = reaction / atr if atr > 0 else 0.0
    duration = swing.pivot_index - prev_opposite.pivot_index if prev_opposite else 1
    duration_score = min(1.0, duration / sc.duration_cap)
    volume_score = _volume_score(candles, swing)
    wick_score = _wick_ratio_score(candles, swing)
    displacement = _displacement_score(candles, swing, atr, sc.displacement_divisor)
    trend_q = _trend_quality_score(candles, swing, prev_opposite)

    components = {
        "leg_size": min(1.0, leg_atr / sc.leg_atr_divisor) * 100,
        "atr_multiple": min(1.0, leg_atr / sc.atr_divisor) * 100,
        "reaction_size": min(1.0, reaction_atr / sc.reaction_divisor) * 100,
        "duration": duration_score * 100,
        "volume": volume_score * 100,
        "wick_ratio": wick_score * 100,
        "displacement": displacement * 100,
        "trend_quality": trend_q * 100,
    }

    raw = sum(components[k] * weights.get(k, 0.0) for k in components)
    if not swing.confirmed:
        raw *= 0.85

    normalized = min(sc.normalized_max, raw)
    swing.score = round(raw, 2)
    swing.normalized_score = round(normalized, 2)
    swing.strength = _score_to_level(normalized, config)
    swing.reasoning.extend([
        f"leg_atr={leg_atr:.2f}",
        f"raw_score={raw:.1f}",
        f"normalized_score={normalized:.1f}",
        f"strength={swing.strength}",
    ])
    swing.metadata["strength_components"] = {k: round(v, 2) for k, v in components.items()}
    swing.metadata["raw_score"] = round(raw, 2)
    swing.metadata["normalized_score"] = round(normalized, 2)
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


def _reaction_size(candles: list[Candle], swing: InternalSwing, bars: int) -> float:
    end = min(len(candles), swing.pivot_index + bars + 1)
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


def _wick_ratio_score(candles: list[Candle], swing: InternalSwing) -> float:
    c = candles[swing.pivot_index]
    body = max(abs(c.close - c.open), 1e-12)
    if swing.direction == SwingDirection.HIGH:
        wick = c.high - max(c.open, c.close)
    else:
        wick = min(c.open, c.close) - c.low
    return min(1.0, wick / body)


def _displacement_score(candles: list[Candle], swing: InternalSwing, atr: float, divisor: float) -> float:
    if swing.confirmation_index is None or atr <= 0:
        return 0.5
    c = candles[swing.confirmation_index]
    if swing.direction == SwingDirection.HIGH:
        disp = swing.price - c.low
    else:
        disp = c.high - swing.price
    return min(1.0, (disp / atr) / divisor)


def _trend_quality_score(
    candles: list[Candle],
    swing: InternalSwing,
    prev_opposite: InternalSwing | None,
) -> float:
    if not prev_opposite:
        return 0.5
    if swing.direction == SwingDirection.HIGH:
        return 1.0 if swing.price > prev_opposite.price else 0.3
    return 1.0 if swing.price < prev_opposite.price else 0.3


def _score_to_level(score: float, config: SwingEngineConfig) -> int:
    for level, threshold in enumerate(config.strength.level_thresholds, start=1):
        if score < threshold:
            return level
    return len(config.strength.level_thresholds) + 1

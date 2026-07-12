"""Swing Quality Score (Sprint 3, Priority 2).

Produces a 0-100 quality score per swing from weighted sub-factors so
downstream modules (BOS, CHoCH, Decision Engine) can automatically ignore
low-quality swings. This is *advisory* metadata: it never changes which swings
are detected, only annotates them.

Factors (each normalized 0-100):
    confirmation      - confirmed + low delay
    displacement      - impulse away from the pivot
    wick              - rejection wick relative to body
    atr_normalization - leg size relative to ATR (structural significance)
    leg_symmetry      - balance vs the prior opposite leg
    liquidity_sweep   - did the pivot sweep a recent extreme then reverse
    trend_alignment   - agreement with prevailing structure
"""

from __future__ import annotations

from shared.types.models import Candle

from swing_engine.config import SwingEngineConfig
from swing_engine.models import DetectedSwing, SwingDirection
from swing_engine.utils import atr_at


def _confirmation_factor(swing: DetectedSwing) -> float:
    if not swing.confirmed:
        return 25.0
    penalty = min(60.0, swing.confirmation_delay * 8.0)
    return max(40.0, 100.0 - penalty)


def _displacement_factor(swing: DetectedSwing) -> float:
    comp = swing.metadata.get("strength_components", {})
    return float(comp.get("displacement", 50.0))


def _wick_factor(swing: DetectedSwing) -> float:
    comp = swing.metadata.get("strength_components", {})
    return float(comp.get("wick_ratio", 50.0))


def _atr_norm_factor(swing: DetectedSwing) -> float:
    leg_atr = float(swing.metadata.get("leg_atr", 0.0))
    return max(0.0, min(100.0, (leg_atr / 2.0) * 100.0))


def _leg_symmetry_factor(
    swing: DetectedSwing,
    prev_opposite: DetectedSwing | None,
    prev_same: DetectedSwing | None,
) -> float:
    if not prev_opposite or not prev_same:
        return 50.0
    cur_leg = abs(swing.price - prev_opposite.price)
    prev_leg = abs(prev_opposite.price - prev_same.price)
    if cur_leg <= 0 or prev_leg <= 0:
        return 50.0
    ratio = min(cur_leg, prev_leg) / max(cur_leg, prev_leg)
    return ratio * 100.0


def _liquidity_sweep_factor(
    swing: DetectedSwing,
    candles: list[Candle],
    atr_series: list[float],
    config: SwingEngineConfig,
) -> float:
    idx = swing.pivot_index
    lb = config.quality.sweep_lookback_bars
    start = max(0, idx - lb)
    if start >= idx:
        return 50.0
    atr = atr_at(idx, atr_series, candles)
    pen = config.quality.sweep_penetration_atr * atr
    prior = candles[start:idx]
    if swing.direction == SwingDirection.HIGH:
        prior_high = max(c.high for c in prior)
        swept = swing.price >= prior_high + pen
    else:
        prior_low = min(c.low for c in prior)
        swept = swing.price <= prior_low - pen
    if not swept:
        return 40.0
    # Reversal after the sweep raises quality further.
    after = candles[idx + 1 : idx + 1 + config.confirmation.delay_bars + 1]
    if after:
        if swing.direction == SwingDirection.HIGH:
            reversed_ = min(c.close for c in after) < swing.price - pen
        else:
            reversed_ = max(c.close for c in after) > swing.price + pen
        return 100.0 if reversed_ else 70.0
    return 70.0


def _trend_alignment_factor(swing: DetectedSwing) -> float:
    comp = swing.metadata.get("strength_components", {})
    return float(comp.get("trend_quality", 50.0))


def compute_quality_score(
    swing: DetectedSwing,
    prev_same: DetectedSwing | None,
    prev_opposite: DetectedSwing | None,
    candles: list[Candle],
    atr_series: list[float],
    config: SwingEngineConfig,
) -> tuple[float, dict[str, float]]:
    factors = {
        "confirmation": _confirmation_factor(swing),
        "displacement": _displacement_factor(swing),
        "wick": _wick_factor(swing),
        "atr_normalization": _atr_norm_factor(swing),
        "leg_symmetry": _leg_symmetry_factor(swing, prev_opposite, prev_same),
        "liquidity_sweep": _liquidity_sweep_factor(swing, candles, atr_series, config),
        "trend_alignment": _trend_alignment_factor(swing),
    }
    weights = config.quality.weights
    total_w = sum(weights.get(k, 0.0) for k in factors) or 1.0
    score = sum(factors[k] * weights.get(k, 0.0) for k in factors) / total_w
    return round(max(0.0, min(100.0, score)), 1), factors

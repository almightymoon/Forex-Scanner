"""Score-gated swing confirmation (v1.4.0).

Hard gates (always block):
  - insufficient bars
  - pivot level violated during hold window

Soft factors (weighted 0-100):
  - ATR reaction, displacement, wick quality, structure break
  - trend alignment, liquidity sweep, volume, hold quality

confirmed = confirmation_score >= threshold
"""

from __future__ import annotations

from shared.types.models import Candle

from swing_engine.config import ConfirmationScoreConfig, SwingEngineConfig
from swing_engine.models import PivotCandidate, SwingDirection
from swing_engine.utils import atr_at


def compute_confirmation_score(
    pivot: PivotCandidate,
    candles: list[Candle],
    atr_series: list[float],
    config: SwingEngineConfig,
    *,
    prev_opposite: PivotCandidate | None,
    prev_same: PivotCandidate | None,
    conf_index: int | None,
    delay: int,
    mtf_alignment: float = 0.5,
) -> tuple[float, dict[str, float], list[dict]]:
    """Return (score 0-100, factor map, audit checks with passed/blocking flags)."""
    cs = config.confirmation_score
    idx = pivot.pivot_index
    atr = atr_at(idx, atr_series, candles)
    factors: dict[str, float] = {}
    checks: list[dict] = []

    # Hold quality — did price respect pivot through min_candles?
    hold = _hold_quality(pivot, candles, config.confirmation.min_candles)
    factors["hold_quality"] = hold
    checks.append(_check("hold_quality", "Held pivot level", hold, 50, hold >= 50, blocking=True))

    # ATR reaction after pivot
    reaction_atr = _reaction_atr(pivot, candles, atr, config.strength.reaction_bars)
    reaction_score = min(100.0, (reaction_atr / 1.5) * 100.0)
    factors["atr_reaction"] = reaction_score
    checks.append(_check("atr_reaction", "ATR reaction", reaction_atr, 1.5, reaction_atr >= 1.0))

    # Displacement from pivot
    disp_atr = _displacement_atr(pivot, candles, atr, config.confirmation.displacement_bars)
    disp_score = min(100.0, (disp_atr / 0.5) * 100.0)
    factors["displacement"] = disp_score
    checks.append(_check("displacement", "Displacement", disp_atr, 0.35, disp_atr >= 0.15))

    # Wick quality at pivot bar
    wick = _wick_score(pivot, candles)
    factors["wick"] = wick
    checks.append(_check("wick", "Wick quality", wick, 40, wick >= 30))

    # Structure break vs previous opposite
    struct = _structure_score(pivot, prev_opposite)
    factors["structure_break"] = struct
    checks.append(_check("structure_break", "Structure break", struct, 50, struct >= 40))

    # Trend alignment vs prior leg
    trend = _trend_score(pivot, prev_opposite)
    factors["trend_alignment"] = trend
    checks.append(_check("trend_alignment", "Trend alignment", trend, 50, trend >= 40))

    # Liquidity sweep
    sweep = _sweep_score(pivot, candles, atr, config)
    factors["liquidity_sweep"] = sweep
    checks.append(_check("liquidity_sweep", "Liquidity sweep", sweep, 50, sweep >= 50, blocking=False))

    # Volume at pivot
    vol = _volume_score(pivot, candles)
    factors["volume"] = vol
    checks.append(_check("volume", "Volume", vol, 40, vol >= 35))

    # MTF parent agreement
    mtf_score = mtf_alignment * 100.0
    factors["mtf_alignment"] = mtf_score
    checks.append(_check("mtf_alignment", "Parent TF agreement", mtf_score, 50, mtf_score >= 45))

    # Confirmation delay penalty
    delay_penalty = max(0.0, 100.0 - delay * 8.0)
    factors["delay"] = delay_penalty

    weights = cs.weights
    total_w = sum(weights.get(k, 0.0) for k in factors) or 1.0
    score = sum(factors[k] * weights.get(k, 0.0) for k in factors) / total_w
    return round(max(0.0, min(100.0, score)), 1), factors, checks


def _check(
    rule_id: str, label: str, value: float, threshold: float, passed: bool, *, blocking: bool = False
) -> dict:
    return {
        "rule_id": rule_id,
        "label": label,
        "value": round(value, 2),
        "threshold": threshold,
        "passed": passed,
        "blocking": blocking,
    }


def _hold_quality(pivot: PivotCandidate, candles: list[Candle], min_candles: int) -> float:
    idx = pivot.pivot_index
    if idx + min_candles >= len(candles):
        return 0.0
    for j in range(1, min_candles + 1):
        bar = candles[idx + j]
        if pivot.direction == SwingDirection.HIGH and bar.high > pivot.price:
            return 0.0
        if pivot.direction == SwingDirection.LOW and bar.low < pivot.price:
            return 0.0
    return 100.0


def _reaction_atr(pivot: PivotCandidate, candles: list[Candle], atr: float, bars: int) -> float:
    end = min(len(candles), pivot.pivot_index + bars + 1)
    if pivot.pivot_index + 1 >= end or atr <= 0:
        return 0.0
    seg = candles[pivot.pivot_index + 1 : end]
    if pivot.direction == SwingDirection.HIGH:
        reaction = pivot.price - min(c.low for c in seg)
    else:
        reaction = max(c.high for c in seg) - pivot.price
    return reaction / atr


def _displacement_atr(pivot: PivotCandidate, candles: list[Candle], atr: float, bars: int) -> float:
    if atr <= 0:
        return 0.0
    end = min(len(candles), pivot.pivot_index + bars + 1)
    seg = candles[pivot.pivot_index + 1 : end]
    if not seg:
        return 0.0
    if pivot.direction == SwingDirection.HIGH:
        disp = pivot.price - min(c.low for c in seg)
    else:
        disp = max(c.high for c in seg) - pivot.price
    return disp / atr


def _wick_score(pivot: PivotCandidate, candles: list[Candle]) -> float:
    c = candles[pivot.pivot_index]
    body = max(abs(c.close - c.open), 1e-12)
    if pivot.direction == SwingDirection.HIGH:
        wick = c.high - max(c.open, c.close)
    else:
        wick = min(c.open, c.close) - c.low
    return min(100.0, (wick / body) * 100.0)


def _structure_score(pivot: PivotCandidate, prev_opposite: PivotCandidate | None) -> float:
    if not prev_opposite:
        return 50.0
    if pivot.direction == SwingDirection.HIGH:
        return 100.0 if pivot.price > prev_opposite.price else 25.0
    return 100.0 if pivot.price < prev_opposite.price else 25.0


def _trend_score(pivot: PivotCandidate, prev_opposite: PivotCandidate | None) -> float:
    return _structure_score(pivot, prev_opposite)


def _sweep_score(
    pivot: PivotCandidate, candles: list[Candle], atr: float, config: SwingEngineConfig
) -> float:
    lb = config.quality.sweep_lookback_bars
    start = max(0, pivot.pivot_index - lb)
    if start >= pivot.pivot_index or atr <= 0:
        return 40.0
    pen = config.quality.sweep_penetration_atr * atr
    prior = candles[start : pivot.pivot_index]
    if pivot.direction == SwingDirection.HIGH:
        swept = pivot.price >= max(c.high for c in prior) + pen
    else:
        swept = pivot.price <= min(c.low for c in prior) - pen
    return 85.0 if swept else 35.0


def _volume_score(pivot: PivotCandidate, candles: list[Candle]) -> float:
    idx = pivot.pivot_index
    if idx < 5 or not candles[idx].volume:
        return 50.0
    window = [candles[j].volume for j in range(max(0, idx - 10), idx) if candles[j].volume]
    if not window:
        return 50.0
    avg = sum(window) / len(window)
    return min(100.0, (candles[idx].volume / avg) * 50.0)

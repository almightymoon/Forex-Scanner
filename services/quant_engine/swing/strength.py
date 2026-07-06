"""Swing strength scoring (0–100) — institutional significance."""

from __future__ import annotations

from shared.types.models import Candle

from services.quant_engine.swing.models import Swing, SwingSide


def _candle_momentum(candles: list[Candle], index: int, side: SwingSide) -> float:
    """Body-to-range ratio of the swing candle, direction-aligned."""
    if index < 0 or index >= len(candles):
        return 0.5
    c = candles[index]
    rng = max(c.high - c.low, 1e-9)
    body = abs(c.close - c.open)
    ratio = body / rng
    if side == SwingSide.HIGH:
        return ratio if c.close < c.open else ratio * 0.7
    return ratio if c.close > c.open else ratio * 0.7


def _prominence(candles: list[Candle], index: int, price: float, side: SwingSide, lookback: int) -> float:
    left = max(0, index - lookback)
    right = min(len(candles), index + lookback + 1)
    window = candles[left:right]
    if not window:
        return 0.0
    if side == SwingSide.HIGH:
        return price - min(c.low for c in window)
    return max(c.high for c in window) - price


def _reaction_strength(candles: list[Candle], index: int, price: float, side: SwingSide, bars: int = 3) -> float:
    """How sharply price reacted after the swing formed."""
    end = min(len(candles), index + bars + 1)
    if index + 1 >= end:
        return 0.5
    segment = candles[index + 1 : end]
    if side == SwingSide.HIGH:
        drop = price - min(c.low for c in segment)
    else:
        drop = max(c.high for c in segment) - price
    return drop


def _break_significance(
    swing: Swing,
    prev_same: Swing | None,
    prev_opposite: Swing | None,
) -> float:
    """Score how meaningfully this swing breaks prior structure."""
    if prev_same is None:
        return 0.5
    if swing.side == SwingSide.HIGH:
        if prev_same and swing.price > prev_same.price:
            return 1.0
        if prev_opposite and swing.price > prev_opposite.price:
            return 0.85
        return 0.3
    if prev_same and swing.price < prev_same.price:
        return 1.0
    if prev_opposite and swing.price < prev_opposite.price:
        return 0.85
    return 0.3


def calculate_strength(
    swing: Swing,
    candles: list[Candle],
    atr_at_index: list[float],
    prev_swing: Swing | None,
    prev_same_side: Swing | None,
    lookback: int,
) -> float:
    """
    Composite strength score 0–100.

    Factors: displacement, momentum, ATR distance, time gap, break significance, reaction.
    """
    atr = atr_at_index[swing.index] if swing.index < len(atr_at_index) else 1.0
    atr = max(atr, 1e-9)

    disp = abs(swing.price - prev_swing.price) if prev_swing else atr
    disp_atr = disp / atr
    disp_score = min(1.0, disp_atr / 2.5)

    prom = _prominence(candles, swing.index, swing.price, swing.side, lookback)
    prom_score = min(1.0, prom / (atr * 2.0))

    momentum = _candle_momentum(candles, swing.index, swing.side)

    if prev_swing:
        bars_since = swing.index - prev_swing.index
        time_score = min(1.0, bars_since / 20.0)
    else:
        time_score = 0.5

    break_sig = _break_significance(swing, prev_same_side, prev_swing)
    reaction = _reaction_strength(candles, swing.index, swing.price, swing.side)
    reaction_score = min(1.0, reaction / (atr * 1.5)) if reaction > 0 else 0.4

    raw = (
        disp_score * 25.0
        + prom_score * 20.0
        + momentum * 15.0
        + time_score * 10.0
        + break_sig * 15.0
        + reaction_score * 15.0
    )

    if not swing.confirmed:
        raw *= 0.85

    if swing.tier.value == "major":
        raw = min(100.0, raw * 1.08)

    return round(min(100.0, max(0.0, raw)), 1)


def rescore_swings(
    swings: list[Swing],
    candles: list[Candle],
    atr_at_index: list[float],
    lookback: int,
) -> list[Swing]:
    """Recompute strength for an ordered swing list."""
    scored: list[Swing] = []
    last_same: dict[SwingSide, Swing | None] = {SwingSide.HIGH: None, SwingSide.LOW: None}

    for i, swing in enumerate(swings):
        prev = swings[i - 1] if i > 0 else None
        prev_same = last_same[swing.side]
        strength = calculate_strength(swing, candles, atr_at_index, prev, prev_same, lookback)
        updated = Swing(
            id=swing.id,
            symbol=swing.symbol,
            timeframe=swing.timeframe,
            timestamp=swing.timestamp,
            price=swing.price,
            index=swing.index,
            side=swing.side,
            confirmed=swing.confirmed,
            strength=strength,
            tier=swing.tier,
            scope=swing.scope,
            lookback=swing.lookback,
            lookforward=swing.lookforward,
            metadata={**swing.metadata, "strength_factors": swing.metadata.get("strength_factors", {})},
        )
        scored.append(updated)
        last_same[swing.side] = updated

    return scored

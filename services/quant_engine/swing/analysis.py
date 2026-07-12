"""
Market structure helpers built on scanner.swing_detection.

BOS/CHoCH classification remains here for backward compatibility until
market_structure sprint extracts it.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from shared.types.models import Candle, TrendDirection

from swing_engine import SwingEngine, get_config
from swing_engine.models import DetectedSwing, SwingDirection


@dataclass
class SwingPoint:
    """Legacy swing point — maps from production Swing model."""

    index: int
    price: float
    kind: str  # "high" | "low"
    strength: float = 0.0
    displacement_atr: float = 0.0


@dataclass
class MarketStructureState:
    swings: list[SwingPoint] = field(default_factory=list)
    swing_highs: list[SwingPoint] = field(default_factory=list)
    swing_lows: list[SwingPoint] = field(default_factory=list)
    direction: TrendDirection = TrendDirection.RANGING
    last_event: str | None = None
    event_direction: str | None = None
    bos_kind: str = "external"
    continuation: bool = True
    swing_strength_avg: float = 0.0
    sequence: list[str] = field(default_factory=list)


@dataclass
class TrendContext:
    direction: TrendDirection = TrendDirection.RANGING
    strength: float = 0.0
    maturity: str = "developing"
    compression: bool = False
    expansion: bool = False
    pullback: bool = False
    swing_highs: list[SwingPoint] = field(default_factory=list)
    swing_lows: list[SwingPoint] = field(default_factory=list)
    structure: MarketStructureState | None = None
    reasons: list[str] = field(default_factory=list)


def _swing_to_point(swing: DetectedSwing) -> SwingPoint:
    return SwingPoint(
        index=swing.pivot_index,
        price=swing.price,
        kind=swing.direction.value.lower(),
        strength=swing.score,
        displacement_atr=float(swing.metadata.get("leg_atr", 0.0)),
    )


def build_zigzag_swings(
    candles: list[Candle],
    lookback: int = 3,
    min_atr_mult: float = 0.35,
) -> list[SwingPoint]:
    """Backward-compatible zigzag swings via SwingDetectionEngine."""
    if not candles:
        return []

    tf = candles[0].timeframe
    base = get_config(tf)
    cfg = replace(
        base,
        pivot=replace(base.pivot, left_lookback=lookback, right_lookback=lookback),
        leg=replace(base.leg, min_atr_multiple=min_atr_mult),
        atr=replace(base.atr, validation_multiplier=min_atr_mult),
    )
    result = SwingEngine(cfg).detect(candles)
    return [_swing_to_point(s) for s in result.swings]


def find_swings(candles: list[Candle], lookback: int = 3) -> tuple[list[SwingPoint], list[SwingPoint]]:
    swings = build_zigzag_swings(candles, lookback=lookback)
    highs = [s for s in swings if s.kind == "high"]
    lows = [s for s in swings if s.kind == "low"]
    return highs, lows


def analyze_market_structure(candles: list[Candle], lookback: int = 3) -> MarketStructureState:
    """Derive BOS/CHoCH, internal/external structure, and swing sequence from swings."""
    state = MarketStructureState()
    swings = build_zigzag_swings(candles, lookback=lookback)
    state.swings = swings
    state.swing_highs = [s for s in swings if s.kind == "high"]
    state.swing_lows = [s for s in swings if s.kind == "low"]

    if state.swing_highs:
        strengths = [s.strength for s in state.swing_highs[-3:]] + [s.strength for s in state.swing_lows[-3:]]
        state.swing_strength_avg = sum(strengths) / len(strengths) if strengths else 0.0

    if len(state.swing_highs) >= 2 and len(state.swing_lows) >= 2:
        hh = state.swing_highs[-1].price > state.swing_highs[-2].price
        hl = state.swing_lows[-1].price > state.swing_lows[-2].price
        lh = state.swing_highs[-1].price < state.swing_highs[-2].price
        ll = state.swing_lows[-1].price < state.swing_lows[-2].price

        if hh:
            state.sequence.append("HH")
        else:
            state.sequence.append("LH")
        if hl:
            state.sequence.append("HL")
        else:
            state.sequence.append("LL")

        if hh and hl:
            state.direction = TrendDirection.BULLISH
        elif lh and ll:
            state.direction = TrendDirection.BEARISH

        price = candles[-1].close
        prev_high = state.swing_highs[-2].price
        prev_low = state.swing_lows[-2].price

        if price > state.swing_highs[-1].price and state.swing_highs[-1].price > prev_high:
            state.last_event = "bos"
            state.event_direction = "buy"
            state.continuation = state.direction == TrendDirection.BULLISH
        elif price < state.swing_lows[-1].price and state.swing_lows[-1].price < prev_low:
            state.last_event = "bos"
            state.event_direction = "sell"
            state.continuation = state.direction == TrendDirection.BEARISH
        elif hh and not hl and state.direction != TrendDirection.BULLISH:
            state.last_event = "choch"
            state.event_direction = "buy"
            state.continuation = False
        elif ll and not lh and state.direction != TrendDirection.BEARISH:
            state.last_event = "choch"
            state.event_direction = "sell"
            state.continuation = False

    if candles:
        state.bos_kind = classify_bos(state.swing_highs, state.swing_lows, candles[-1].close)
    return state


def analyze_trend_context(candles: list[Candle], ema20: float | None, ema50: float | None) -> TrendContext:
    ctx = TrendContext()
    if len(candles) < 20:
        return ctx

    structure = analyze_market_structure(candles)
    ctx.structure = structure
    ctx.swing_highs = structure.swing_highs[-4:]
    ctx.swing_lows = structure.swing_lows[-4:]

    recent = candles[-20:]
    ranges = [c.high - c.low for c in recent]
    avg_range = sum(ranges[:-5]) / max(len(ranges[:-5]), 1)
    last_range = sum(ranges[-5:]) / 5

    if last_range < avg_range * 0.7:
        ctx.compression = True
        ctx.reasons.append("Volatility compression — coiling before expansion")
    elif last_range > avg_range * 1.3:
        ctx.expansion = True
        ctx.reasons.append("Volatility expansion — trend impulse active")

    if structure.direction != TrendDirection.RANGING:
        ctx.direction = structure.direction
        avg_str = structure.swing_strength_avg / 100 if structure.swing_strength_avg else 0.5
        ctx.strength = min(1.0, 0.4 + avg_str * 0.6)
        if structure.continuation:
            ctx.reasons.append(f"Swing structure: {' · '.join(structure.sequence)} — trend continuation")
        elif structure.last_event == "choch":
            ctx.reasons.append("CHoCH detected — potential trend reversal")
        else:
            ctx.reasons.append(f"Swing structure: {' · '.join(structure.sequence)}")

    price = candles[-1].close
    if ema20 and ema50 and ctx.direction == TrendDirection.BULLISH:
        if price < ema20 and price > ema50:
            ctx.pullback = True
            ctx.reasons.append("Healthy bullish pullback to EMA zone")
    elif ema20 and ema50 and ctx.direction == TrendDirection.BEARISH:
        if price > ema20 and price < ema50:
            ctx.pullback = True
            ctx.reasons.append("Healthy bearish pullback to EMA zone")

    bars_in_trend = 0
    for c in reversed(candles[-30:]):
        if ema20 and ema50:
            if ctx.direction == TrendDirection.BULLISH and c.close > ema50:
                bars_in_trend += 1
            elif ctx.direction == TrendDirection.BEARISH and c.close < ema50:
                bars_in_trend += 1
            else:
                break
    if bars_in_trend > 20:
        ctx.maturity = "mature"
        ctx.reasons.append("Mature trend — watch for exhaustion")
    elif bars_in_trend > 8:
        ctx.maturity = "established"
    else:
        ctx.maturity = "developing"

    return ctx


def classify_bos(swing_highs: list[SwingPoint], swing_lows: list[SwingPoint], price: float) -> str:
    if not swing_highs or not swing_lows:
        return "external"
    range_size = swing_highs[-1].price - swing_lows[-1].price
    if range_size <= 0:
        return "external"
    mid = swing_lows[-1].price + range_size * 0.5
    if (price > swing_lows[-1].price and price < mid) or (price < swing_highs[-1].price and price > mid):
        return "internal"
    return "external"


def session_from_hour(hour: int) -> str:
    if 0 <= hour < 8:
        return "asia"
    if 8 <= hour < 13:
        return "london"
    if 13 <= hour < 16:
        return "london_ny_overlap"
    if 13 <= hour < 21:
        return "new_york"
    return "off_hours"


def detect_session_liquidity(candles: list[Candle]) -> list[str]:
    tags: list[str] = []
    if len(candles) < 24:
        return tags

    asia = [c for c in candles[-24:] if session_from_hour(c.timestamp.hour) == "asia"]
    if not asia:
        return tags

    asia_high = max(c.high for c in asia)
    asia_low = min(c.low for c in asia)
    last = candles[-1]

    if last.high > asia_high and last.close < asia_high:
        tags.append("London/NY sweep of Asian high")
    if last.low < asia_low and last.close > asia_low:
        tags.append("London/NY sweep of Asian low")
    if last.high <= asia_high and last.low >= asia_low:
        tags.append("Price respecting Asian liquidity range")

    return tags

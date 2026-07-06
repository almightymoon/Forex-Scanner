"""Robust swing detection and market structure analysis — foundation for all SMC engines."""

from dataclasses import dataclass, field

from shared.types.models import Candle, TrendDirection


@dataclass
class SwingPoint:
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


def _atr(candles: list[Candle], period: int = 14) -> float:
    if len(candles) < 2:
        return 0.0
    trs: list[float] = []
    for i in range(1, min(len(candles), period + 1)):
        c, prev = candles[i], candles[i - 1]
        tr = max(c.high - c.low, abs(c.high - prev.close), abs(c.low - prev.close))
        trs.append(tr)
    return sum(trs) / len(trs) if trs else candles[-1].high - candles[-1].low


def _raw_fractals(candles: list[Candle], lookback: int) -> list[SwingPoint]:
    """Fractal pivots — local extrema over `lookback` bars each side."""
    pivots: list[SwingPoint] = []
    if len(candles) < lookback * 2 + 1:
        return pivots

    for i in range(lookback, len(candles) - lookback):
        is_high = all(candles[i].high >= candles[i - j].high for j in range(1, lookback + 1)) and all(
            candles[i].high >= candles[i + j].high for j in range(1, lookback + 1)
        )
        is_low = all(candles[i].low <= candles[i - j].low for j in range(1, lookback + 1)) and all(
            candles[i].low <= candles[i + j].low for j in range(1, lookback + 1)
        )
        if is_high:
            pivots.append(SwingPoint(i, candles[i].high, "high"))
        elif is_low:
            pivots.append(SwingPoint(i, candles[i].low, "low"))
    return pivots


def _score_swing(
    swing: SwingPoint,
    prev: SwingPoint | None,
    candles: list[Candle],
    atr: float,
    lookback: int,
) -> SwingPoint:
    disp = abs(swing.price - prev.price) if prev else atr
    swing.displacement_atr = disp / atr if atr > 0 else 1.0

    left = max(0, swing.index - lookback)
    right = min(len(candles), swing.index + lookback + 1)
    window = candles[left:right]
    if swing.kind == "high":
        prominence = swing.price - min(c.low for c in window)
    else:
        prominence = max(c.high for c in window) - swing.price

    prom_score = min(1.0, prominence / (atr * 2)) if atr > 0 else 0.5
    disp_score = min(1.0, swing.displacement_atr / 2.0)
    age_bars = len(candles) - 1 - swing.index
    recency = max(0.3, 1.0 - age_bars / 50)

    swing.strength = round((disp_score * 40 + prom_score * 35 + recency * 25), 1)
    return swing


def build_zigzag_swings(
    candles: list[Candle],
    lookback: int = 3,
    min_atr_mult: float = 0.35,
) -> list[SwingPoint]:
    """
    Zigzag-filtered alternating swings.
    Filters noise via ATR minimum displacement and keeps strongest same-type pivots.
    """
    if len(candles) < lookback * 2 + 3:
        return []

    atr = _atr(candles)
    min_move = atr * min_atr_mult
    raw = _raw_fractals(candles, lookback)
    if not raw:
        return []

    zigzag: list[SwingPoint] = []
    for pivot in raw:
        if not zigzag:
            zigzag.append(pivot)
            continue

        last = zigzag[-1]
        if pivot.kind == last.kind:
            if pivot.kind == "high" and pivot.price >= last.price:
                zigzag[-1] = pivot
            elif pivot.kind == "low" and pivot.price <= last.price:
                zigzag[-1] = pivot
            continue

        if abs(pivot.price - last.price) < min_move:
            continue
        zigzag.append(pivot)

    scored: list[SwingPoint] = []
    for i, s in enumerate(zigzag):
        prev = zigzag[i - 1] if i > 0 else None
        scored.append(_score_swing(s, prev, candles, atr, lookback))
    return scored


def find_swings(candles: list[Candle], lookback: int = 3) -> tuple[list[SwingPoint], list[SwingPoint]]:
    """Backward-compatible API — returns zigzag-filtered highs and lows separately."""
    swings = build_zigzag_swings(candles, lookback=lookback)
    highs = [s for s in swings if s.kind == "high"]
    lows = [s for s in swings if s.kind == "low"]
    return highs, lows


def analyze_market_structure(candles: list[Candle], lookback: int = 3) -> MarketStructureState:
    """Derive BOS/CHoCH, internal/external structure, and swing sequence from zigzag swings."""
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

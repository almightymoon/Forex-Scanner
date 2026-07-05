"""Shared swing and price-structure analysis for SMC engines."""

from dataclasses import dataclass, field

from shared.types.models import Candle, TrendDirection


@dataclass
class SwingPoint:
    index: int
    price: float
    kind: str  # "high" | "low"


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
    reasons: list[str] = field(default_factory=list)


def find_swings(candles: list[Candle], lookback: int = 3) -> tuple[list[SwingPoint], list[SwingPoint]]:
    highs: list[SwingPoint] = []
    lows: list[SwingPoint] = []
    if len(candles) < lookback * 2 + 1:
        return highs, lows

    for i in range(lookback, len(candles) - lookback):
        if all(candles[i].high >= candles[i - j].high for j in range(1, lookback + 1)) and all(
            candles[i].high >= candles[i + j].high for j in range(1, lookback + 1)
        ):
            highs.append(SwingPoint(i, candles[i].high, "high"))
        if all(candles[i].low <= candles[i - j].low for j in range(1, lookback + 1)) and all(
            candles[i].low <= candles[i + j].low for j in range(1, lookback + 1)
        ):
            lows.append(SwingPoint(i, candles[i].low, "low"))
    return highs, lows


def analyze_trend_context(candles: list[Candle], ema20: float | None, ema50: float | None) -> TrendContext:
    ctx = TrendContext()
    if len(candles) < 20:
        return ctx

    highs, lows = find_swings(candles)
    ctx.swing_highs = highs[-4:]
    ctx.swing_lows = lows[-4:]

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

    if len(highs) >= 2 and len(lows) >= 2:
        hh = highs[-1].price > highs[-2].price
        hl = lows[-1].price > lows[-2].price
        lh = highs[-1].price < highs[-2].price
        ll = lows[-1].price < lows[-2].price
        if hh and hl:
            ctx.direction = TrendDirection.BULLISH
            ctx.strength = min(1.0, 0.5 + (highs[-1].price - lows[-1].price) / highs[-1].price * 10)
            ctx.reasons.append("Swing structure: higher highs and higher lows")
        elif lh and ll:
            ctx.direction = TrendDirection.BEARISH
            ctx.strength = min(1.0, 0.5 + (highs[-1].price - lows[-1].price) / highs[-1].price * 10)
            ctx.reasons.append("Swing structure: lower highs and lower lows")

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
    """Internal vs external BOS based on swing range relative to recent structure."""
    if not swing_highs or not swing_lows:
        return "external"
    range_size = swing_highs[-1].price - swing_lows[-1].price
    if range_size <= 0:
        return "external"
    mid = swing_lows[-1].price + range_size * 0.5
    return "internal" if (price > swing_lows[-1].price and price < mid) or (price < swing_highs[-1].price and price > mid) else "external"


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
    """Tag liquidity events by session (Asian range, London/NY sweep)."""
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

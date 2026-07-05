"""Risk engine — config-driven support/resistance, volume, spread rules."""

from typing import Optional

from shared.config.scanner import ScoringConfig, get_scanner_config
from shared.types.models import (
    Candle,
    IndicatorValues,
    NewsContext,
    RiskLevel,
    SignalDirection,
    TrendDirection,
)

from .models import SRAnalysis, VolumeAnalysis


class RiskEngine:
    def __init__(self, config: ScoringConfig | None = None):
        self.config = config or get_scanner_config().scoring

    def analyze_support_resistance(
        self,
        candles: list[Candle],
        indicators: IndicatorValues,
        trend: TrendDirection,
    ) -> SRAnalysis:
        cfg = self.config
        rules = cfg.risk_sr.rules
        result = SRAnalysis()
        score = 0
        if not candles:
            return result

        price = candles[-1].close
        recent_low = min(c.low for c in candles[-20:])
        recent_high = max(c.high for c in candles[-20:])

        if trend == TrendDirection.BULLISH and abs(price - recent_low) / price < 0.005:
            result.near_support = True
            score += rules["near_support"].points
            result.reasons.append("Price near support zone")
        elif trend == TrendDirection.BEARISH and abs(price - recent_high) / price < 0.005:
            result.near_resistance = True
            score += rules["near_resistance"].points
            result.reasons.append("Price near resistance zone")

        if indicators.bb_lower and indicators.bb_upper:
            range_size = indicators.bb_upper - indicators.bb_lower
            if range_size > 0:
                fib_618 = indicators.bb_lower + range_size * 0.618
                if abs(price - fib_618) / price < 0.003:
                    result.fib_confluence = True
                    score += rules["fib_confluence"].points
                    result.reasons.append("Fibonacci 61.8% confluence")

        if indicators.bb_middle:
            if trend == TrendDirection.BULLISH and price > indicators.bb_middle:
                result.pivot_confirmed = True
                score += rules["pivot_confirmed"].points
                result.reasons.append("Price above pivot/Bollinger midline")
            elif trend == TrendDirection.BEARISH and price < indicators.bb_middle:
                result.pivot_confirmed = True
                score += rules["pivot_confirmed"].points
                result.reasons.append("Price below pivot/Bollinger midline")

        result.score = min(score, cfg.risk_sr.max_points)
        return result

    def analyze_volume(self, candles: list[Candle], indicators: IndicatorValues) -> VolumeAnalysis:
        cfg = self.config
        rules = cfg.risk_volume.rules
        result = VolumeAnalysis()
        score = 0

        if len(candles) >= 20:
            avg_vol = sum(c.volume for c in candles[-20:]) / 20
            if candles[-1].volume > avg_vol * 1.2:
                result.volume_above_avg = True
                score += rules["volume_above_avg"].points
                result.reasons.append("Volume above 20-period average")

        if indicators.atr_14:
            result.atr_expanding = True
            score += rules["atr_expanding"].points
            result.reasons.append("ATR expansion confirms volatility")

        if len(candles) >= 2:
            last = candles[-1]
            body = abs(last.close - last.open)
            wick = last.high - last.low
            if wick > 0 and body / wick > 0.6:
                result.breakout_strength = True
                score += rules["breakout_strength"].points
                result.reasons.append("Strong breakout candle body")

        if candles and candles[-1].spread is not None:
            if candles[-1].spread > cfg.spread_warning:
                result.spread_normal = False
                score = max(0, score + rules["spread_penalty"].points)
                result.reasons.append("Warning: elevated spread")

        result.score = min(score, cfg.risk_volume.max_points)
        return result

    def assess_risk(self, score: int, news: NewsContext, spread_ok: bool) -> RiskLevel:
        if not spread_ok or (
            news.has_high_impact_soon
            and news.minutes_until_event
            and news.minutes_until_event <= 15
        ):
            return RiskLevel.HIGH
        if score >= 85 and not news.has_high_impact_soon:
            return RiskLevel.LOW
        if score >= 70:
            return RiskLevel.MEDIUM
        return RiskLevel.HIGH

    def calculate_levels(
        self,
        candles: list[Candle],
        indicators: IndicatorValues,
        direction: SignalDirection,
    ) -> tuple[
        Optional[tuple[float, float]],
        Optional[float],
        Optional[float],
        Optional[float],
        Optional[float],
        Optional[float],
    ]:
        if not candles or direction == SignalDirection.NEUTRAL:
            return None, None, None, None, None, None

        price = candles[-1].close
        atr = indicators.atr_14 or (price * 0.001)

        if direction == SignalDirection.BUY:
            entry = (price - atr * 0.2, price + atr * 0.1)
            sl = price - atr * 1.5
            tp1 = price + atr * 2
            tp2 = price + atr * 3
            tp3 = price + atr * 5
        else:
            entry = (price - atr * 0.1, price + atr * 0.2)
            sl = price + atr * 1.5
            tp1 = price - atr * 2
            tp2 = price - atr * 3
            tp3 = price - atr * 5

        risk = abs(price - sl)
        reward = abs(tp1 - price)
        rr = round(reward / risk, 2) if risk > 0 else None

        return entry, sl, tp1, tp2, tp3, rr

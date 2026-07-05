"""Trend scoring engine — config-driven rules."""

from shared.config.scanner import ScoringConfig, get_scanner_config
from shared.types.models import Candle, IndicatorValues, TrendDirection

from .models import TrendAnalysis


class TrendEngine:
    def __init__(self, config: ScoringConfig | None = None):
        self.config = config or get_scanner_config().scoring

    def analyze(self, candles: list[Candle], indicators: IndicatorValues) -> TrendAnalysis:
        cfg = self.config
        rules = cfg.trend.rules
        result = TrendAnalysis()
        score = 0
        price = candles[-1].close if candles else 0

        if indicators.ema_20 and indicators.ema_50 and indicators.ema_200:
            if indicators.ema_20 > indicators.ema_50 > indicators.ema_200:
                result.ema_aligned = True
                result.direction = TrendDirection.BULLISH
                score += rules["ema_alignment"].points
                result.reasons.append("EMA 20 > 50 > 200 aligned bullish")
            elif indicators.ema_20 < indicators.ema_50 < indicators.ema_200:
                result.ema_aligned = True
                result.direction = TrendDirection.BEARISH
                score += rules["ema_alignment"].points
                result.reasons.append("EMA 20 < 50 < 200 aligned bearish")

        if indicators.adx_14 and indicators.adx_14 > cfg.adx_threshold:
            result.adx_strong = True
            score += rules["adx_strong"].points
            result.reasons.append(f"ADX strong at {indicators.adx_14:.1f}")

        if len(candles) >= 10:
            highs = [c.high for c in candles[-10:]]
            lows = [c.low for c in candles[-10:]]
            mid = len(highs) // 2
            if max(highs[mid:]) > max(highs[:mid]):
                result.higher_highs = True
                score += rules["higher_highs"].points
                result.reasons.append("Higher highs detected")
            if min(lows[mid:]) > min(lows[:mid]):
                result.higher_lows = True
                score += rules["higher_lows"].points
                result.reasons.append("Higher lows detected")

        if indicators.vwap and price > indicators.vwap:
            result.price_above_vwap = True
            score += rules["price_above_vwap"].points
            result.reasons.append("Price above VWAP")

        result.score = min(score, cfg.trend.max_points)
        return result

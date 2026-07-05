"""Trend scoring engine — EMA alignment, ADX, structure, VWAP."""

from shared.types.models import Candle, IndicatorValues, TrendDirection

from .models import TrendAnalysis

MAX_TREND = 20


class TrendEngine:
    def analyze(self, candles: list[Candle], indicators: IndicatorValues) -> TrendAnalysis:
        result = TrendAnalysis()
        score = 0
        price = candles[-1].close if candles else 0

        if indicators.ema_20 and indicators.ema_50 and indicators.ema_200:
            if indicators.ema_20 > indicators.ema_50 > indicators.ema_200:
                result.ema_aligned = True
                result.direction = TrendDirection.BULLISH
                score += 8
                result.reasons.append("EMA 20 > 50 > 200 aligned bullish")
            elif indicators.ema_20 < indicators.ema_50 < indicators.ema_200:
                result.ema_aligned = True
                result.direction = TrendDirection.BEARISH
                score += 8
                result.reasons.append("EMA 20 < 50 < 200 aligned bearish")

        if indicators.adx_14 and indicators.adx_14 > 25:
            result.adx_strong = True
            score += 5
            result.reasons.append(f"ADX strong at {indicators.adx_14:.1f}")

        if len(candles) >= 10:
            highs = [c.high for c in candles[-10:]]
            lows = [c.low for c in candles[-10:]]
            mid = len(highs) // 2
            if max(highs[mid:]) > max(highs[:mid]):
                result.higher_highs = True
                score += 3
                result.reasons.append("Higher highs detected")
            if min(lows[mid:]) > min(lows[:mid]):
                result.higher_lows = True
                score += 2
                result.reasons.append("Higher lows detected")

        if indicators.vwap and price > indicators.vwap:
            result.price_above_vwap = True
            score += 2
            result.reasons.append("Price above VWAP")

        result.score = min(score, MAX_TREND)
        return result

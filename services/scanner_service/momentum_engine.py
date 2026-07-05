"""Momentum scoring engine — MACD, RSI, ATR."""

from shared.types.models import IndicatorValues, TrendDirection

from .models import MomentumAnalysis

MAX_MOMENTUM = 15


class MomentumEngine:
    def analyze(self, indicators: IndicatorValues, trend: TrendDirection) -> MomentumAnalysis:
        result = MomentumAnalysis()
        score = 0

        if indicators.macd_histogram is not None:
            if trend == TrendDirection.BULLISH and indicators.macd_histogram > 0:
                result.macd_bullish = True
                score += 5
                result.reasons.append("MACD histogram bullish")
            elif trend == TrendDirection.BEARISH and indicators.macd_histogram < 0:
                result.macd_bullish = True
                score += 5
                result.reasons.append("MACD histogram bearish")

        if indicators.rsi_14 is not None:
            if trend == TrendDirection.BULLISH and 50 <= indicators.rsi_14 <= 70:
                result.rsi_in_zone = True
                score += 5
                result.reasons.append(f"RSI in bullish zone ({indicators.rsi_14:.1f})")
            elif trend == TrendDirection.BEARISH and 30 <= indicators.rsi_14 <= 50:
                result.rsi_in_zone = True
                score += 5
                result.reasons.append(f"RSI in bearish zone ({indicators.rsi_14:.1f})")

        if indicators.atr_14:
            result.atr_rising = True
            score += 5
            result.reasons.append("ATR indicating volatility expansion")

        result.score = min(score, MAX_MOMENTUM)
        return result

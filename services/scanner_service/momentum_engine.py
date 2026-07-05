"""Momentum scoring engine — config-driven rules."""

from shared.config.scanner import ScoringConfig, get_scanner_config
from shared.types.models import IndicatorValues, TrendDirection

from .models import MomentumAnalysis


class MomentumEngine:
    def __init__(self, config: ScoringConfig | None = None):
        self.config = config or get_scanner_config().scoring

    def analyze(self, indicators: IndicatorValues, trend: TrendDirection) -> MomentumAnalysis:
        cfg = self.config
        rules = cfg.momentum.rules
        result = MomentumAnalysis()
        score = 0

        if indicators.macd_histogram is not None:
            if trend == TrendDirection.BULLISH and indicators.macd_histogram > 0:
                result.macd_bullish = True
                score += rules["macd_histogram"].points
                result.reasons.append("MACD histogram bullish")
            elif trend == TrendDirection.BEARISH and indicators.macd_histogram < 0:
                result.macd_bullish = True
                score += rules["macd_histogram"].points
                result.reasons.append("MACD histogram bearish")

        if indicators.rsi_14 is not None:
            if trend == TrendDirection.BULLISH and cfg.rsi_bullish_min <= indicators.rsi_14 <= cfg.rsi_bullish_max:
                result.rsi_in_zone = True
                score += rules["rsi_in_zone"].points
                result.reasons.append(f"RSI in bullish zone ({indicators.rsi_14:.1f})")
            elif trend == TrendDirection.BEARISH and cfg.rsi_bearish_min <= indicators.rsi_14 <= cfg.rsi_bearish_max:
                result.rsi_in_zone = True
                score += rules["rsi_in_zone"].points
                result.reasons.append(f"RSI in bearish zone ({indicators.rsi_14:.1f})")

        if indicators.atr_14:
            result.atr_rising = True
            score += rules["atr_expansion"].points
            result.reasons.append("ATR indicating volatility expansion")

        result.score = min(score, cfg.momentum.max_points)
        return result

"""Momentum scoring engine — RSI, MACD, ATR, Stochastic."""

from shared.config.scoring_loader import V2ScoringConfig, get_v2_scoring_config
from shared.types.models import IndicatorValues, TrendDirection

from services.quant_engine.confidence.output import EngineOutput, clamp_score, confidence_from_score
from services.quant_engine.decision.models import MomentumAnalysis


class MomentumEngine:
    def __init__(self, config: V2ScoringConfig | None = None):
        self._v2 = config or get_v2_scoring_config()

    def run(self, candles_count: int, indicators: IndicatorValues) -> EngineOutput:
        analysis = self._analyze(indicators, TrendDirection.RANGING)
        max_score = self._v2.weights.momentum
        direction = "NEUTRAL"
        if indicators.macd_histogram and indicators.macd_histogram > 0:
            direction = "BUY"
        elif indicators.macd_histogram and indicators.macd_histogram < 0:
            direction = "SELL"

        return EngineOutput(
            name="Momentum",
            score=clamp_score(analysis.score, max_score),
            max_score=max_score,
            confidence=confidence_from_score(analysis.score, max_score),
            direction=direction,
            reasons=analysis.reasons,
            metadata={"bars": candles_count},
        )

    def analyze(self, indicators: IndicatorValues, trend: TrendDirection) -> MomentumAnalysis:
        return self._analyze(indicators, trend)

    def _analyze(self, indicators: IndicatorValues, trend: TrendDirection) -> MomentumAnalysis:
        rules = self._v2.rules.get("momentum", {})
        thresholds = self._v2.thresholds
        max_score = self._v2.weights.momentum
        result = MomentumAnalysis()
        score = 0

        if indicators.macd_histogram is not None:
            if (trend == TrendDirection.BULLISH and indicators.macd_histogram > 0) or (
                trend == TrendDirection.BEARISH and indicators.macd_histogram < 0
            ) or trend == TrendDirection.RANGING:
                if indicators.macd_histogram != 0:
                    result.macd_bullish = indicators.macd_histogram > 0
                    score += rules.get("macd", 4)
                    result.reasons.append(
                        "MACD histogram bullish" if indicators.macd_histogram > 0 else "MACD histogram bearish"
                    )

        rsi_min_b = float(thresholds.get("rsi_bullish_min", 50))
        rsi_max_b = float(thresholds.get("rsi_bullish_max", 70))
        rsi_min_s = float(thresholds.get("rsi_bearish_min", 30))
        rsi_max_s = float(thresholds.get("rsi_bearish_max", 50))

        if indicators.rsi_14 is not None:
            if rsi_min_b <= indicators.rsi_14 <= rsi_max_b:
                result.rsi_in_zone = True
                score += rules.get("rsi", 4)
                result.reasons.append(f"RSI in bullish zone ({indicators.rsi_14:.1f})")
            elif rsi_min_s <= indicators.rsi_14 <= rsi_max_s:
                result.rsi_in_zone = True
                score += rules.get("rsi", 4)
                result.reasons.append(f"RSI in bearish zone ({indicators.rsi_14:.1f})")

        if indicators.stoch_k is not None and indicators.stoch_d is not None:
            if indicators.stoch_k > indicators.stoch_d:
                score += rules.get("stochastic", 3)
                result.reasons.append("Stochastic momentum bullish")
            elif indicators.stoch_k < indicators.stoch_d:
                score += rules.get("stochastic", 3)
                result.reasons.append("Stochastic momentum bearish")

        if indicators.atr_14:
            result.atr_rising = True
            score += rules.get("atr_momentum", 3)
            result.reasons.append("ATR indicating momentum expansion")

        result.score = clamp_score(score, max_score)
        return result

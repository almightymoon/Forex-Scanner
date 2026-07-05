"""Trend scoring engine — config-driven, returns standardized EngineOutput."""

from shared.config.scoring_loader import V2ScoringConfig, get_v2_scoring_config
from shared.types.models import Candle, IndicatorValues, TrendDirection

from .engine_output import EngineOutput, clamp_score, confidence_from_score
from .models import TrendAnalysis


class TrendEngine:
    def __init__(self, config: V2ScoringConfig | None = None):
        self._v2 = config or get_v2_scoring_config()

    def run(self, candles: list[Candle], indicators: IndicatorValues) -> EngineOutput:
        analysis = self._analyze(candles, indicators)
        direction = "NEUTRAL"
        if analysis.direction == TrendDirection.BULLISH:
            direction = "BUY"
        elif analysis.direction == TrendDirection.BEARISH:
            direction = "SELL"

        max_score = self._v2.weights.trend
        return EngineOutput(
            name="Trend",
            score=clamp_score(analysis.score, max_score),
            max_score=max_score,
            confidence=confidence_from_score(analysis.score, max_score),
            direction=direction,
            reasons=analysis.reasons,
            metadata={
                "ema_aligned": analysis.ema_aligned,
                "adx_strong": analysis.adx_strong,
                "trend_strength": analysis.score / max_score if max_score else 0,
            },
        )

    def analyze(self, candles: list[Candle], indicators: IndicatorValues) -> TrendAnalysis:
        """Backward-compatible analysis object."""
        return self._analyze(candles, indicators)

    def _analyze(self, candles: list[Candle], indicators: IndicatorValues) -> TrendAnalysis:
        rules = self._v2.rules.get("trend", {})
        thresholds = self._v2.thresholds
        adx_threshold = float(thresholds.get("adx", 25))
        max_score = self._v2.weights.trend

        result = TrendAnalysis()
        score = 0
        price = candles[-1].close if candles else 0

        if indicators.ema_20 and indicators.ema_50 and indicators.ema_200:
            if indicators.ema_20 > indicators.ema_50 > indicators.ema_200:
                result.ema_aligned = True
                result.direction = TrendDirection.BULLISH
                score += rules.get("ema_alignment", 8)
                result.reasons.append("EMA20 above EMA50 above EMA200")
            elif indicators.ema_20 < indicators.ema_50 < indicators.ema_200:
                result.ema_aligned = True
                result.direction = TrendDirection.BEARISH
                score += rules.get("ema_alignment", 8)
                result.reasons.append("EMA20 below EMA50 below EMA200")

        if indicators.sma_20 and indicators.ema_50:
            if price > indicators.sma_20 > indicators.ema_50:
                score += rules.get("sma_alignment", 4)
                result.reasons.append("Price above SMA20, SMA aligned bullish")
            elif price < indicators.sma_20 < indicators.ema_50:
                score += rules.get("sma_alignment", 4)
                result.reasons.append("Price below SMA20, SMA aligned bearish")

        if indicators.adx_14 and indicators.adx_14 > adx_threshold:
            result.adx_strong = True
            score += rules.get("adx_strong", 4)
            result.reasons.append(f"ADX strong at {indicators.adx_14:.1f}")

        if len(candles) >= 10:
            highs = [c.high for c in candles[-10:]]
            lows = [c.low for c in candles[-10:]]
            mid = len(highs) // 2
            if max(highs[mid:]) > max(highs[:mid]):
                result.higher_highs = True
                score += rules.get("higher_highs", 2)
                result.reasons.append("Higher highs detected")
            if min(lows[mid:]) > min(lows[:mid]):
                result.higher_lows = True
                score += rules.get("higher_lows", 2)
                result.reasons.append("Higher lows detected")
            if max(highs[mid:]) < max(highs[:mid]):
                score += rules.get("lower_highs", 2)
                result.reasons.append("Lower highs detected")
            if min(lows[mid:]) < min(lows[:mid]):
                score += rules.get("lower_lows", 2)
                result.reasons.append("Lower lows detected")

        if indicators.vwap and price > indicators.vwap:
            result.price_above_vwap = True
            score += rules.get("price_above_vwap", 2)
            result.reasons.append("Price above VWAP")
        elif indicators.vwap and price < indicators.vwap:
            score += rules.get("price_above_vwap", 2)
            result.reasons.append("Price below VWAP")

        result.score = clamp_score(score, max_score)
        return result

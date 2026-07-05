"""Risk engine — S/R, trade quality, levels (orchestrated output)."""

from typing import Optional

from shared.config.scoring_loader import V2ScoringConfig, get_v2_scoring_config
from shared.types.models import (
    Candle,
    IndicatorValues,
    NewsContext,
    RiskLevel,
    SignalDirection,
    TrendDirection,
)

from .engine_output import EngineOutput, clamp_score, confidence_from_score
from .models import SRAnalysis, VolumeAnalysis


class RiskEngine:
    def __init__(self, config: V2ScoringConfig | None = None):
        self._v2 = config or get_v2_scoring_config()

    def run(
        self,
        candles: list[Candle],
        indicators: IndicatorValues,
        trend: TrendDirection,
        direction: SignalDirection,
    ) -> EngineOutput:
        sr = self.analyze_support_resistance(candles, indicators, trend)
        max_score = self._v2.weights.risk
        rules = self._v2.rules.get("risk", {"near_level": 3, "rr_quality": 3})
        score = min(sr.score, rules.get("near_level", 3) * 2)

        _, sl, tp1, _, _, rr = self.calculate_levels(candles, indicators, direction)
        reasons = list(sr.reasons)
        warnings: list[str] = []

        if rr and rr >= 2:
            score += rules.get("rr_quality", 3)
            reasons.append(f"Favorable risk/reward ({rr}:1)")
        elif rr and rr < 1.5:
            warnings.append("Suboptimal risk/reward ratio")

        score = clamp_score(score, max_score)
        return EngineOutput(
            name="Risk",
            score=score,
            max_score=max_score,
            confidence=confidence_from_score(score, max_score),
            direction="NEUTRAL",
            reasons=reasons,
            warnings=warnings,
            metadata={"stop_loss": sl, "take_profit_1": tp1, "risk_reward": rr},
        )

    def analyze_support_resistance(
        self,
        candles: list[Candle],
        indicators: IndicatorValues,
        trend: TrendDirection,
    ) -> SRAnalysis:
        result = SRAnalysis()
        score = 0
        if not candles:
            return result

        price = candles[-1].close
        recent_low = min(c.low for c in candles[-20:])
        recent_high = max(c.high for c in candles[-20:])

        if trend == TrendDirection.BULLISH and abs(price - recent_low) / price < 0.005:
            result.near_support = True
            score += 3
            result.reasons.append("Price near support zone")
        elif trend == TrendDirection.BEARISH and abs(price - recent_high) / price < 0.005:
            result.near_resistance = True
            score += 3
            result.reasons.append("Price near resistance zone")

        if indicators.bb_lower and indicators.bb_upper:
            range_size = indicators.bb_upper - indicators.bb_lower
            if range_size > 0:
                fib_618 = indicators.bb_lower + range_size * 0.618
                if abs(price - fib_618) / price < 0.003:
                    result.fib_confluence = True
                    score += 2
                    result.reasons.append("Fibonacci 61.8% confluence")

        if indicators.bb_middle:
            if trend == TrendDirection.BULLISH and price > indicators.bb_middle:
                result.pivot_confirmed = True
                score += 2
                result.reasons.append("Price above pivot/Bollinger midline")
            elif trend == TrendDirection.BEARISH and price < indicators.bb_middle:
                result.pivot_confirmed = True
                score += 2
                result.reasons.append("Price below pivot/Bollinger midline")

        result.score = score
        return result

    def analyze_volume(self, candles: list[Candle], indicators: IndicatorValues) -> VolumeAnalysis:
        result = VolumeAnalysis()
        score = 0
        spread_warn = float(self._v2.thresholds.get("spread_warning", 0.0005))

        if len(candles) >= 20:
            avg_vol = sum(c.volume for c in candles[-20:]) / 20
            if candles[-1].volume > avg_vol * 1.2:
                result.volume_above_avg = True
                score += 2
                result.reasons.append("Volume above 20-period average")

        if indicators.atr_14:
            result.atr_expanding = True
            score += 2
            result.reasons.append("ATR expansion confirms volatility")

        if candles and candles[-1].spread is not None:
            if candles[-1].spread > spread_warn:
                result.spread_normal = False
                result.reasons.append("Warning: elevated spread")

        result.score = score
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

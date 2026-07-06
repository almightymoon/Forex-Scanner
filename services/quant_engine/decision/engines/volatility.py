"""Volatility engine — ATR, spread, candle size, session volatility."""

from shared.config.scoring_loader import V2ScoringConfig, get_v2_scoring_config
from shared.types.models import Candle, IndicatorValues

from services.quant_engine.confidence.output import EngineOutput, clamp_score, confidence_from_score
from services.quant_engine.decision.session import current_session


class VolatilityEngine:
    def __init__(self, config: V2ScoringConfig | None = None):
        self.config = config or get_v2_scoring_config()

    def run(self, candles: list[Candle], indicators: IndicatorValues) -> EngineOutput:
        weights = self.config.weights
        rules = self.config.rules.get("volatility", {"atr": 2, "spread": 2, "candle_size": 2})
        thresholds = self.config.thresholds
        spread_warn = float(thresholds.get("spread_warning", 0.0005))

        score = 0
        reasons: list[str] = []
        warnings: list[str] = []

        if indicators.atr_14:
            score += rules.get("atr", 2)
            reasons.append("ATR indicates active volatility")

        if candles and candles[-1].spread is not None:
            if candles[-1].spread <= spread_warn:
                score += rules.get("spread", 2)
                reasons.append("Spread within normal range")
            else:
                warnings.append("Elevated spread — volatility risk")

        if len(candles) >= 20:
            avg_body = sum(abs(c.close - c.open) for c in candles[-20:]) / 20
            last_body = abs(candles[-1].close - candles[-1].open)
            if last_body > avg_body * 1.1:
                score += rules.get("candle_size", 2)
                reasons.append("Above-average candle body size")

        session = current_session()
        if session in ("london", "new_york", "london_ny_overlap"):
            reasons.append(f"Active session volatility ({session.replace('_', ' ')})")

        score = clamp_score(score, weights.volatility)
        if indicators.atr_14 and candles:
            atr_pct = indicators.atr_14 / candles[-1].close
            if atr_pct > 0.003:
                warnings.append("High ATR relative to price")

        return EngineOutput(
            name="Volatility",
            score=score,
            max_score=weights.volatility,
            confidence=confidence_from_score(score, weights.volatility),
            direction="NEUTRAL",
            reasons=reasons,
            warnings=warnings,
            metadata={"session": session},
        )

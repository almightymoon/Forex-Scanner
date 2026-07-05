"""Fair Value Gap engine — bullish/bearish FVG scoring."""

from shared.config.scoring_loader import V2ScoringConfig, get_v2_scoring_config
from shared.types.models import SMCPattern, SignalDirection

from .engine_output import EngineOutput, clamp_score, confidence_from_score
from .pattern_scoring import filter_patterns


class FairValueGapEngine:
    def __init__(self, config: V2ScoringConfig | None = None):
        self.config = config or get_v2_scoring_config()

    def run(self, patterns: list[SMCPattern]) -> EngineOutput:
        weights = self.config.weights
        rules = self.config.rules.get("fair_value_gap", {
            "bullish_fvg": 5, "bearish_fvg": 5, "filled": 2,
        })
        fvgs = filter_patterns(patterns, {"fvg"})
        score = 0
        reasons: list[str] = []
        buy_pts = sell_pts = 0

        for p in fvgs:
            gap_size = p.metadata.get("gap_size", 0)
            if p.direction == SignalDirection.BUY:
                score += rules.get("bullish_fvg", 5)
                if gap_size and gap_size > 0:
                    reasons.append(f"Bullish FVG (gap {gap_size:.5f})")
                else:
                    reasons.append("Bullish Fair Value Gap")
                buy_pts += 1
            else:
                score += rules.get("bearish_fvg", 5)
                reasons.append("Bearish Fair Value Gap")
                sell_pts += 1

        score = clamp_score(score, weights.fair_value_gap)
        direction = "BUY" if buy_pts > sell_pts else "SELL" if sell_pts > buy_pts else "NEUTRAL"
        return EngineOutput(
            name="Fair Value Gap",
            score=score,
            max_score=weights.fair_value_gap,
            confidence=confidence_from_score(score, weights.fair_value_gap),
            direction=direction,
            reasons=reasons,
            metadata={"gap_count": len(fvgs)},
        )

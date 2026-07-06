"""Multi-Timeframe engine — M15, H1, H4, D1 alignment."""

from shared.config.scoring_loader import V2ScoringConfig, get_v2_scoring_config
from shared.types.models import TrendDirection

from services.quant_engine.confidence.output import EngineOutput, clamp_score, confidence_from_score


class MultiTimeframeEngine:
    def __init__(self, config: V2ScoringConfig | None = None):
        self.config = config or get_v2_scoring_config()

    def run(
        self,
        mtf_trends: dict[str, TrendDirection],
        primary_trend: TrendDirection,
    ) -> EngineOutput:
        max_score = self.config.weights.multi_timeframe
        timeframes = ["M15", "H1", "H4", "D1"]
        aligned = 0
        checked = 0
        reasons: list[str] = []
        breakdown: dict[str, str] = {}

        for tf in timeframes:
            t = mtf_trends.get(tf)
            if t and t != TrendDirection.RANGING:
                checked += 1
                breakdown[tf] = t.value
                if t == primary_trend:
                    aligned += 1
                    reasons.append(f"{tf} aligned ({t.value})")
                else:
                    reasons.append(f"{tf} divergent ({t.value})")

        if checked == 0:
            score = max_score // 2
            reasons = ["Insufficient MTF data — neutral score"]
        else:
            score = int((aligned / checked) * max_score)

        score = clamp_score(score, max_score)
        direction = "NEUTRAL"
        if primary_trend == TrendDirection.BULLISH and aligned == checked and checked > 0:
            direction = "BUY"
        elif primary_trend == TrendDirection.BEARISH and aligned == checked and checked > 0:
            direction = "SELL"

        return EngineOutput(
            name="Multi-Timeframe",
            score=score,
            max_score=max_score,
            confidence=confidence_from_score(score, max_score),
            direction=direction,
            reasons=reasons,
            metadata={"aligned": aligned, "checked": checked, "timeframes": breakdown},
        )

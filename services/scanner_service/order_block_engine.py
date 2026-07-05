"""Order Block engine — bullish/bearish OB detection scoring."""

from shared.config.scoring_loader import V2ScoringConfig, get_v2_scoring_config
from shared.types.models import SMCPattern, SignalDirection

from .engine_output import EngineOutput, clamp_score, confidence_from_score
from .pattern_scoring import filter_patterns


class OrderBlockEngine:
    def __init__(self, config: V2ScoringConfig | None = None):
        self.config = config or get_v2_scoring_config()

    def run(self, patterns: list[SMCPattern]) -> EngineOutput:
        weights = self.config.weights
        rules = self.config.rules.get("order_block", {"bullish_ob": 6, "bearish_ob": 6, "fresh_ob": 4})
        obs = filter_patterns(patterns, {"order_block"})
        score = 0
        reasons: list[str] = []
        buy_pts = sell_pts = 0

        for p in obs[-3:]:
            is_fresh = p.metadata.get("index", 0) >= 0
            if p.direction == SignalDirection.BUY:
                score += rules.get("bullish_ob", 6)
                if is_fresh:
                    score += rules.get("fresh_ob", 4)
                reasons.append("Bullish Order Block" + (" (fresh)" if is_fresh else ""))
                buy_pts += 1
            else:
                score += rules.get("bearish_ob", 6)
                if is_fresh:
                    score += rules.get("fresh_ob", 4)
                reasons.append("Bearish Order Block" + (" (fresh)" if is_fresh else ""))
                sell_pts += 1

        score = clamp_score(score, weights.order_block)
        direction = "BUY" if buy_pts > sell_pts else "SELL" if sell_pts > buy_pts else "NEUTRAL"
        return EngineOutput(
            name="Order Block",
            score=score,
            max_score=weights.order_block,
            confidence=confidence_from_score(score, weights.order_block),
            direction=direction,
            reasons=reasons,
            metadata={"count": len(obs)},
        )

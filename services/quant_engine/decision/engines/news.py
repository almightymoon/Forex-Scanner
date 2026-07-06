"""News engine — calendar risk, blocking status."""

from shared.config.scoring_loader import V2ScoringConfig, get_v2_scoring_config
from shared.types.models import NewsContext, NewsImpact

from services.quant_engine.confidence.output import EngineOutput, clamp_score, confidence_from_score


class NewsEngine:
    def __init__(self, config: V2ScoringConfig | None = None):
        self._v2 = config or get_v2_scoring_config()

    def run(self, news: NewsContext) -> EngineOutput:
        max_score = self._v2.weights.news
        rules = self._v2.rules.get("news", {"clear": 5, "medium": 3, "high_soon": 1, "blocked": 0})
        score = rules.get("clear", 5)
        reasons: list[str] = []
        warnings: list[str] = []
        blocked = False

        if news.has_high_impact_soon:
            if news.minutes_until_event and news.minutes_until_event <= 30:
                score = rules.get("blocked", 0)
                blocked = True
                warnings.append(
                    f"High-impact news in {news.minutes_until_event} min — trading blocked"
                )
                reasons.append(news.event_title or "High-impact event imminent")
            else:
                score = rules.get("high_soon", 1)
                warnings.append(f"Medium/high news approaching: {news.event_title or 'event'}")
                reasons.append("High-impact news within 2 hours")
        elif news.impact == NewsImpact.MEDIUM:
            score = rules.get("medium", 3)
            reasons.append("Medium-impact event on calendar")
        else:
            reasons.append("No high-impact news in the next 2 hours")

        score = clamp_score(score, max_score)
        return EngineOutput(
            name="News",
            score=score,
            max_score=max_score,
            confidence=confidence_from_score(score, max_score),
            direction="NEUTRAL",
            reasons=reasons,
            warnings=warnings,
            metadata={"blocked": blocked, "impact": news.impact.value},
        )

    def score(self, news: NewsContext) -> int:
        return self.run(news).score

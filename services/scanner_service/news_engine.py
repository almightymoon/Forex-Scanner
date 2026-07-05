"""News scoring engine — evaluates calendar risk for a symbol."""

from shared.types.models import NewsContext

from .score_engine import ScoreEngine


class NewsEngine:
    """Thin wrapper around news scoring for independent testing."""

    def __init__(self):
        self._score = ScoreEngine()

    def score(self, news: NewsContext) -> int:
        return self._score.score_news(news)

"""Compute confidence and structured decision factors for v2 output."""

from shared.config.scanner import ScoringConfig, get_scanner_config
from shared.types.models import MTFAlignment, NewsContext

from services.quant_engine.decision.models import MomentumAnalysis
from services.quant_engine.trend.models import TrendAnalysis
from services.quant_engine.decision.session import current_session, session_weight


def build_decision_factors(
    trend_score: int,
    smc_score: int,
    momentum_score: int,
    sr_score: int,
    volume_score: int,
    mtf_score: int,
    news_score: int,
    trend_reasons: list[str],
    smc_reasons: list[str],
    momentum_reasons: list[str],
    sr_reasons: list[str],
    volume_reasons: list[str],
    mtf: MTFAlignment,
    news: NewsContext,
    config: ScoringConfig | None = None,
) -> list[dict]:
    cfg = config or get_scanner_config().scoring

    def factor(category: str, score: int, max_pts: int, reasons: list[str]) -> dict:
        conf = round(score / max_pts, 2) if max_pts > 0 else 0.0
        return {
            "category": category,
            "score": score,
            "max_score": max_pts,
            "confidence": conf,
            "reasons": reasons,
        }

    factors = [
        factor("trend", trend_score, cfg.trend.max_points, trend_reasons),
        factor("momentum", momentum_score, cfg.momentum.max_points, momentum_reasons),
        factor("smc", smc_score, cfg.smc.max_points, smc_reasons),
        factor("risk", sr_score + volume_score, cfg.risk_sr.max_points + cfg.risk_volume.max_points, sr_reasons + volume_reasons),
        factor("mtf", mtf_score, cfg.mtf.max_points, _mtf_reasons(mtf)),
        factor("news", news_score, cfg.news.max_points, _news_reasons(news)),
    ]
    return factors


def compute_confidence(
    score: int,
    mtf: MTFAlignment,
    spread_ok: bool,
    news: NewsContext,
    session: str | None = None,
    config: ScoringConfig | None = None,
) -> float:
    """0–1 confidence combining score, MTF, spread, news, and session."""
    cfg = config or get_scanner_config().scoring
    base = score / 100.0
    if mtf.aligned:
        base *= 1.08
    elif mtf.score < 5:
        base *= 0.92
    if not spread_ok:
        base *= 0.85
    if news.has_high_impact_soon and news.minutes_until_event and news.minutes_until_event <= 30:
        base *= 0.75
    base *= session_weight(session or current_session(), cfg)
    return round(min(max(base, 0.0), 1.0), 3)


def _mtf_reasons(mtf: MTFAlignment) -> list[str]:
    if mtf.aligned:
        return ["Multi-timeframe alignment confirmed"]
    if mtf.score < 5:
        return ["Timeframes not fully aligned"]
    return [f"Partial MTF alignment ({mtf.score}/10)"]


def _news_reasons(news: NewsContext) -> list[str]:
    if news.has_high_impact_soon:
        title = news.event_title or "high-impact event"
        return [f"Caution: {title} approaching"]
    return ["No high-impact news in the next 2 hours"]

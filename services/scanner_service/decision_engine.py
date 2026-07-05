"""
Decision engine — orchestrates independent scoring engines.

The engine DECIDES trades. AI only explains (see ai_service).
"""

from typing import Optional

from shared.types.models import (
    Candle,
    IndicatorValues,
    NewsContext,
    SMCPattern,
    ScannerSignal,
    Timeframe,
    TrendDirection,
    rating_from_score,
)

from .momentum_engine import MomentumEngine
from .news_engine import NewsEngine
from .risk_engine import RiskEngine
from .score_engine import ScoreEngine
from .smc_engine import SMCScoreEngine
from .trend_engine import TrendEngine


class DecisionEngine:
    """Evaluates market conditions and produces transparent confidence scores."""

    def __init__(self):
        self.trend_engine = TrendEngine()
        self.momentum_engine = MomentumEngine()
        self.smc_engine = SMCScoreEngine()
        self.risk_engine = RiskEngine()
        self.score_engine = ScoreEngine()
        self.news_engine = NewsEngine()

    def evaluate(
        self,
        symbol: str,
        timeframe: Timeframe,
        candles: list[Candle],
        indicators: IndicatorValues,
        smc_patterns: list[SMCPattern],
        mtf_trends: Optional[dict[str, TrendDirection]] = None,
        news: Optional[NewsContext] = None,
    ) -> ScannerSignal:
        trend = self.trend_engine.analyze(candles, indicators)
        smc_score, smc_reasons = self.smc_engine.analyze(smc_patterns, trend.direction)
        momentum = self.momentum_engine.analyze(indicators, trend.direction)
        sr = self.risk_engine.analyze_support_resistance(candles, indicators, trend.direction)
        volume = self.risk_engine.analyze_volume(candles, indicators)
        mtf = self.score_engine.analyze_mtf(mtf_trends or {}, trend.direction)
        news_ctx = news or NewsContext()
        news_score = self.news_engine.score(news_ctx)

        breakdown = self.score_engine.build_breakdown(
            trend.score, smc_score, momentum.score,
            sr.score, volume.score, mtf.score, news_score,
        )

        total = breakdown.total
        direction = self.score_engine.determine_direction(trend.direction, smc_patterns, momentum)
        risk = self.risk_engine.assess_risk(total, news_ctx, volume.spread_normal)
        entry, sl, tp1, tp2, tp3, rr = self.risk_engine.calculate_levels(
            candles, indicators, direction
        )

        technical_reasons = trend.reasons + momentum.reasons + sr.reasons + volume.reasons
        explanation = self.score_engine.generate_explanation(
            symbol, direction, total, trend, smc_reasons, momentum, news_ctx, mtf
        )

        return ScannerSignal(
            symbol=symbol,
            timeframe=timeframe,
            direction=direction,
            score=total,
            rating=rating_from_score(total),
            trend=trend.direction,
            risk_level=risk,
            score_breakdown=breakdown,
            technical_reasons=technical_reasons,
            smc_reasons=smc_reasons,
            news_impact=news_ctx,
            mtf_alignment=mtf,
            entry_zone_low=entry[0] if entry else None,
            entry_zone_high=entry[1] if entry else None,
            stop_loss=sl,
            take_profit_1=tp1,
            take_profit_2=tp2,
            take_profit_3=tp3,
            risk_reward=rr,
            ai_explanation=explanation,
        )

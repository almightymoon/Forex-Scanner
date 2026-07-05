"""Score engine — MTF alignment, news scoring, direction, breakdown assembly."""

from shared.types.models import (
    MTFAlignment,
    NewsContext,
    NewsImpact,
    SMCPattern,
    ScoreBreakdown,
    SignalDirection,
    TrendDirection,
)

from .models import MomentumAnalysis, TrendAnalysis

MAX_MTF = 10
MAX_NEWS = 10


class ScoreEngine:
    def analyze_mtf(
        self, trends: dict[str, TrendDirection], primary_trend: TrendDirection
    ) -> MTFAlignment:
        mtf = MTFAlignment(
            M15=trends.get("M15"),
            H1=trends.get("H1"),
            H4=trends.get("H4"),
            D1=trends.get("D1"),
        )

        aligned_count = 0
        total_checked = 0
        for tf in ["M15", "H1", "H4", "D1"]:
            t = trends.get(tf)
            if t and t != TrendDirection.RANGING:
                total_checked += 1
                if t == primary_trend:
                    aligned_count += 1

        if total_checked > 0:
            mtf.aligned = aligned_count == total_checked
            mtf.score = int((aligned_count / total_checked) * MAX_MTF)
        else:
            mtf.score = 5

        return mtf

    def score_news(self, news: NewsContext) -> int:
        if news.has_high_impact_soon:
            if news.minutes_until_event and news.minutes_until_event <= 30:
                return 0
            return 3
        if news.impact == NewsImpact.MEDIUM:
            return 5
        return MAX_NEWS

    def determine_direction(
        self,
        trend: TrendDirection,
        smc: list[SMCPattern],
        momentum: MomentumAnalysis,
    ) -> SignalDirection:
        bullish_smc = sum(1 for p in smc if p.direction == SignalDirection.BUY)
        bearish_smc = sum(1 for p in smc if p.direction == SignalDirection.SELL)

        if trend == TrendDirection.BULLISH and bullish_smc >= bearish_smc:
            return SignalDirection.BUY
        if trend == TrendDirection.BEARISH and bearish_smc >= bullish_smc:
            return SignalDirection.SELL
        return SignalDirection.NEUTRAL

    def build_breakdown(
        self,
        trend_score: int,
        smc_score: int,
        momentum_score: int,
        sr_score: int,
        volume_score: int,
        mtf_score: int,
        news_score: int,
    ) -> ScoreBreakdown:
        return ScoreBreakdown(
            trend=trend_score,
            smc=smc_score,
            momentum=momentum_score,
            support_resistance=sr_score,
            volume_volatility=volume_score,
            mtf_alignment=mtf_score,
            news_risk=news_score,
        )

    def generate_explanation(
        self,
        symbol: str,
        direction: SignalDirection,
        score: int,
        trend: TrendAnalysis,
        smc_reasons: list[str],
        momentum: MomentumAnalysis,
        news: NewsContext,
        mtf: MTFAlignment,
    ) -> str:
        parts = [f"{symbol} — {direction.value.upper()} — {score}/100", ""]

        if trend.reasons:
            parts.append(f"Trend: {trend.reasons[0]}")
        for r in smc_reasons[:2]:
            parts.append(f"SMC: {r}")
        for r in momentum.reasons[:2]:
            parts.append(f"Momentum: {r}")

        if mtf.aligned:
            parts.append("Multi-timeframe alignment confirmed")
        elif mtf.score < 5:
            parts.append("Warning: timeframes not fully aligned")

        if news.has_high_impact_soon:
            parts.append(f"Caution: {news.event_title or 'high-impact news'} approaching")
        else:
            parts.append("No high-impact news in the next 2 hours")

        return "\n".join(parts)

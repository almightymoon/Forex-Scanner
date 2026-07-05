"""
FX Navigators Decision Engine (v1)

The core intellectual property of Project Atlas.
Every setup starts at 0 and earns points as evidence accumulates.

Score Categories (100 points total):
  - Market Trend:           20
  - Smart Money Concepts:   25
  - Momentum:               15
  - Support/Resistance:     10
  - Volume & Volatility:    10
  - Multi-Timeframe:        10
  - News Risk:              10
"""

from dataclasses import dataclass, field
from typing import Optional

from shared.types.models import (
    Candle,
    ConfidenceRating,
    IndicatorValues,
    MTFAlignment,
    NewsContext,
    NewsImpact,
    RiskLevel,
    SMCPattern,
    ScannerSignal,
    ScoreBreakdown,
    SignalDirection,
    Timeframe,
    TrendDirection,
    rating_from_score,
)


@dataclass
class TrendAnalysis:
    direction: TrendDirection = TrendDirection.RANGING
    ema_aligned: bool = False
    adx_strong: bool = False
    higher_highs: bool = False
    higher_lows: bool = False
    price_above_vwap: bool = False
    score: int = 0
    reasons: list[str] = field(default_factory=list)


@dataclass
class MomentumAnalysis:
    macd_bullish: bool = False
    rsi_in_zone: bool = False
    atr_rising: bool = False
    score: int = 0
    reasons: list[str] = field(default_factory=list)


@dataclass
class SRAnalysis:
    near_support: bool = False
    near_resistance: bool = False
    fib_confluence: bool = False
    pivot_confirmed: bool = False
    score: int = 0
    reasons: list[str] = field(default_factory=list)


@dataclass
class VolumeAnalysis:
    volume_above_avg: bool = False
    atr_expanding: bool = False
    breakout_strength: bool = False
    spread_normal: bool = True
    score: int = 0
    reasons: list[str] = field(default_factory=list)


class DecisionEngine:
    """Evaluates market conditions and produces transparent confidence scores."""

    MAX_TREND = 20
    MAX_SMC = 25
    MAX_MOMENTUM = 15
    MAX_SR = 10
    MAX_VOLUME = 10
    MAX_MTF = 10
    MAX_NEWS = 10

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
        trend = self._analyze_trend(candles, indicators)
        smc_score, smc_reasons = self._analyze_smc(smc_patterns, trend.direction)
        momentum = self._analyze_momentum(indicators, trend.direction)
        sr = self._analyze_support_resistance(candles, indicators, trend.direction)
        volume = self._analyze_volume(candles, indicators)
        mtf = self._analyze_mtf(mtf_trends or {}, trend.direction)
        news_ctx = news or NewsContext()
        news_score = self._score_news(news_ctx)

        breakdown = ScoreBreakdown(
            trend=trend.score,
            smc=smc_score,
            momentum=momentum.score,
            support_resistance=sr.score,
            volume_volatility=volume.score,
            mtf_alignment=mtf.score,
            news_risk=news_score,
        )

        total = breakdown.total
        direction = self._determine_direction(trend.direction, smc_patterns, momentum)
        risk = self._assess_risk(total, news_ctx, volume.spread_normal)
        entry, sl, tp1, tp2, tp3, rr = self._calculate_levels(
            candles, indicators, direction, trend.direction
        )

        technical_reasons = trend.reasons + momentum.reasons + sr.reasons + volume.reasons
        explanation = self._generate_explanation(
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

    def _analyze_trend(
        self, candles: list[Candle], indicators: IndicatorValues
    ) -> TrendAnalysis:
        result = TrendAnalysis()
        score = 0
        price = candles[-1].close if candles else 0

        if indicators.ema_20 and indicators.ema_50 and indicators.ema_200:
            if indicators.ema_20 > indicators.ema_50 > indicators.ema_200:
                result.ema_aligned = True
                result.direction = TrendDirection.BULLISH
                score += 8
                result.reasons.append("EMA 20 > 50 > 200 aligned bullish")
            elif indicators.ema_20 < indicators.ema_50 < indicators.ema_200:
                result.ema_aligned = True
                result.direction = TrendDirection.BEARISH
                score += 8
                result.reasons.append("EMA 20 < 50 < 200 aligned bearish")

        if indicators.adx_14 and indicators.adx_14 > 25:
            result.adx_strong = True
            score += 5
            result.reasons.append(f"ADX strong at {indicators.adx_14:.1f}")

        if len(candles) >= 10:
            highs = [c.high for c in candles[-10:]]
            lows = [c.low for c in candles[-10:]]
            mid = len(highs) // 2
            if max(highs[mid:]) > max(highs[:mid]):
                result.higher_highs = True
                score += 3
                result.reasons.append("Higher highs detected")
            if min(lows[mid:]) > min(lows[:mid]):
                result.higher_lows = True
                score += 2
                result.reasons.append("Higher lows detected")

        if indicators.vwap and price > indicators.vwap:
            result.price_above_vwap = True
            score += 2
            result.reasons.append("Price above VWAP")

        result.score = min(score, self.MAX_TREND)
        return result

    def _analyze_smc(
        self, patterns: list[SMCPattern], trend: TrendDirection
    ) -> tuple[int, list[str]]:
        score = 0
        reasons: list[str] = []
        weights = {
            "bos": 5,
            "choch": 3,
            "order_block": 7,
            "fvg": 4,
            "liquidity_sweep": 6,
            "breaker_block": 5,
            "equal_highs": 3,
            "equal_lows": 3,
        }

        for pattern in patterns:
            w = weights.get(pattern.pattern_type, 2)
            score += w
            label = pattern.pattern_type.replace("_", " ").title()
            reasons.append(f"{label} detected ({pattern.direction.value})")

        return min(score, self.MAX_SMC), reasons

    def _analyze_momentum(
        self, indicators: IndicatorValues, trend: TrendDirection
    ) -> MomentumAnalysis:
        result = MomentumAnalysis()
        score = 0

        if indicators.macd_histogram is not None:
            if trend == TrendDirection.BULLISH and indicators.macd_histogram > 0:
                result.macd_bullish = True
                score += 5
                result.reasons.append("MACD histogram bullish")
            elif trend == TrendDirection.BEARISH and indicators.macd_histogram < 0:
                result.macd_bullish = True
                score += 5
                result.reasons.append("MACD histogram bearish")

        if indicators.rsi_14 is not None:
            if trend == TrendDirection.BULLISH and 50 <= indicators.rsi_14 <= 70:
                result.rsi_in_zone = True
                score += 5
                result.reasons.append(f"RSI in bullish zone ({indicators.rsi_14:.1f})")
            elif trend == TrendDirection.BEARISH and 30 <= indicators.rsi_14 <= 50:
                result.rsi_in_zone = True
                score += 5
                result.reasons.append(f"RSI in bearish zone ({indicators.rsi_14:.1f})")

        if indicators.atr_14:
            result.atr_rising = True
            score += 5
            result.reasons.append("ATR indicating volatility expansion")

        result.score = min(score, self.MAX_MOMENTUM)
        return result

    def _analyze_support_resistance(
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
            score += 5
            result.reasons.append("Price near support zone")
        elif trend == TrendDirection.BEARISH and abs(price - recent_high) / price < 0.005:
            result.near_resistance = True
            score += 5
            result.reasons.append("Price near resistance zone")

        if indicators.bb_lower and indicators.bb_upper:
            range_size = indicators.bb_upper - indicators.bb_lower
            if range_size > 0:
                fib_618 = indicators.bb_lower + range_size * 0.618
                if abs(price - fib_618) / price < 0.003:
                    result.fib_confluence = True
                    score += 3
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

        result.score = min(score, self.MAX_SR)
        return result

    def _analyze_volume(
        self, candles: list[Candle], indicators: IndicatorValues
    ) -> VolumeAnalysis:
        result = VolumeAnalysis()
        score = 0

        if len(candles) >= 20:
            avg_vol = sum(c.volume for c in candles[-20:]) / 20
            if candles[-1].volume > avg_vol * 1.2:
                result.volume_above_avg = True
                score += 4
                result.reasons.append("Volume above 20-period average")

        if indicators.atr_14:
            result.atr_expanding = True
            score += 3
            result.reasons.append("ATR expansion confirms volatility")

        if len(candles) >= 2:
            last = candles[-1]
            body = abs(last.close - last.open)
            wick = last.high - last.low
            if wick > 0 and body / wick > 0.6:
                result.breakout_strength = True
                score += 3
                result.reasons.append("Strong breakout candle body")

        if candles and candles[-1].spread is not None:
            if candles[-1].spread > 0.0005:
                result.spread_normal = False
                score = max(0, score - 5)
                result.reasons.append("Warning: elevated spread")

        result.score = min(score, self.MAX_VOLUME)
        return result

    def _analyze_mtf(
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
            mtf.score = int((aligned_count / total_checked) * self.MAX_MTF)
        else:
            mtf.score = 5  # neutral when no MTF data

        return mtf

    def _score_news(self, news: NewsContext) -> int:
        if news.has_high_impact_soon:
            if news.minutes_until_event and news.minutes_until_event <= 30:
                return 0
            return 3
        if news.impact == NewsImpact.MEDIUM:
            return 5
        return self.MAX_NEWS

    def _determine_direction(
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

    def _assess_risk(
        self, score: int, news: NewsContext, spread_ok: bool
    ) -> RiskLevel:
        if not spread_ok or (news.has_high_impact_soon and news.minutes_until_event and news.minutes_until_event <= 15):
            return RiskLevel.HIGH
        if score >= 85 and not news.has_high_impact_soon:
            return RiskLevel.LOW
        if score >= 70:
            return RiskLevel.MEDIUM
        return RiskLevel.HIGH

    def _calculate_levels(
        self,
        candles: list[Candle],
        indicators: IndicatorValues,
        direction: SignalDirection,
        trend: TrendDirection,
    ) -> tuple[Optional[tuple[float, float]], Optional[float], Optional[float], Optional[float], Optional[float], Optional[float]]:
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

    def _generate_explanation(
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

"""Trend scoring engine — config-driven, returns standardized EngineOutput."""

from shared.config.scoring_loader import V2ScoringConfig, get_v2_scoring_config
from shared.types.models import Candle, IndicatorValues, TrendDirection
from swing_engine.models import SwingScope

from services.quant_engine.features.types import MarketFeatures

from services.quant_engine.confidence.output import EngineOutput, clamp_score, confidence_from_score
from services.quant_engine.market_structure.models import StructureRelation
from services.quant_engine.trend.models import TrendAnalysis
from services.quant_engine.trend.session_context import assess_session_trend
from services.quant_engine.swing_analysis import analyze_trend_context


class TrendEngine:
    def __init__(self, config: V2ScoringConfig | None = None):
        self._v2 = config or get_v2_scoring_config()

    def run(
        self,
        candles: list[Candle],
        indicators: IndicatorValues,
        features: MarketFeatures | None = None,
    ) -> EngineOutput:
        analysis = self._analyze(candles, indicators, features)
        direction = "NEUTRAL"
        if analysis.direction == TrendDirection.BULLISH:
            direction = "BUY"
        elif analysis.direction == TrendDirection.BEARISH:
            direction = "SELL"

        max_score = self._v2.weights.trend
        return EngineOutput(
            name="Trend",
            score=clamp_score(analysis.score, max_score),
            max_score=max_score,
            confidence=confidence_from_score(analysis.score, max_score),
            direction=direction,
            reasons=analysis.reasons,
            metadata={
                "ema_aligned": analysis.ema_aligned,
                "adx_strong": analysis.adx_strong,
                "trend_strength": analysis.trend_strength,
                "maturity": analysis.maturity,
                "compression": analysis.compression,
                "expansion": analysis.expansion,
                "pullback": analysis.pullback,
                "structure_source": (
                    "market_structure_v1"
                    if features and features.structure_snapshot is not None
                    else "legacy_fallback"
                ),
                "session_trend": assess_session_trend(candles).to_dict(),
            },
        )

    def analyze(
        self,
        candles: list[Candle],
        indicators: IndicatorValues,
        features: MarketFeatures | None = None,
    ) -> TrendAnalysis:
        """Backward-compatible analysis object."""
        return self._analyze(candles, indicators, features)

    def _analyze(
        self,
        candles: list[Candle],
        indicators: IndicatorValues,
        features: MarketFeatures | None = None,
    ) -> TrendAnalysis:
        rules = self._v2.rules.get("trend", {})
        thresholds = self._v2.thresholds
        adx_threshold = float(thresholds.get("adx", 25))
        max_score = self._v2.weights.trend

        result = TrendAnalysis()
        score = 0
        price = candles[-1].close if candles else 0

        if indicators.ema_20 and indicators.ema_50 and indicators.ema_200:
            if indicators.ema_20 > indicators.ema_50 > indicators.ema_200:
                result.ema_aligned = True
                result.direction = TrendDirection.BULLISH
                score += rules.get("ema_alignment", 8)
                result.reasons.append("EMA20 above EMA50 above EMA200")
            elif indicators.ema_20 < indicators.ema_50 < indicators.ema_200:
                result.ema_aligned = True
                result.direction = TrendDirection.BEARISH
                score += rules.get("ema_alignment", 8)
                result.reasons.append("EMA20 below EMA50 below EMA200")

        if indicators.sma_20 and indicators.ema_50:
            if price > indicators.sma_20 > indicators.ema_50:
                score += rules.get("sma_alignment", 4)
                result.reasons.append("Price above SMA20, SMA aligned bullish")
            elif price < indicators.sma_20 < indicators.ema_50:
                score += rules.get("sma_alignment", 4)
                result.reasons.append("Price below SMA20, SMA aligned bearish")

        if indicators.adx_14 and indicators.adx_14 > adx_threshold:
            result.adx_strong = True
            score += rules.get("adx_strong", 4)
            result.reasons.append(f"ADX strong at {indicators.adx_14:.1f}")

        # Structure HH/HL/LH/LL from Market Structure Engine v1 — not raw candles.
        score += self._apply_structure_relations(result, features, rules)

        if indicators.vwap and price > indicators.vwap:
            result.price_above_vwap = True
            score += rules.get("price_above_vwap", 2)
            result.reasons.append("Price above VWAP")
        elif indicators.vwap and price < indicators.vwap:
            score += rules.get("price_above_vwap", 2)
            result.reasons.append("Price below VWAP")

        if features and features.trend_context is not None:
            ctx = features.trend_context
        elif features and features.structure_snapshot is not None:
            # Prefer already-mapped feature fields when trend_context is absent.
            ctx = None
        else:
            # Legacy fallback only when no v1 structure features are present.
            ctx = analyze_trend_context(
                candles,
                indicators.ema_20,
                indicators.ema_50,
            )

        if ctx is not None:
            if ctx.direction != TrendDirection.RANGING and result.direction == TrendDirection.RANGING:
                result.direction = ctx.direction
            if ctx.strength > 0.5:
                score += rules.get("swing_structure", 4)
            if ctx.compression:
                score += rules.get("compression", 2)
                result.compression = True
            if ctx.expansion:
                score += rules.get("expansion", 2)
                result.expansion = True
            if ctx.pullback:
                score += rules.get("pullback", 3)
                result.pullback = True
            result.maturity = ctx.maturity
            result.trend_strength = ctx.strength
            for reason in ctx.reasons:
                if reason not in result.reasons:
                    result.reasons.append(reason)
        elif features is not None:
            if (
                features.external_bias is not TrendDirection.RANGING
                and result.direction == TrendDirection.RANGING
            ):
                result.direction = features.external_bias
            if features.trend_strength > 0.5:
                score += rules.get("swing_structure", 4)
            if features.compression:
                score += rules.get("compression", 2)
                result.compression = True
            if features.expansion:
                score += rules.get("expansion", 2)
                result.expansion = True
            if features.pullback:
                score += rules.get("pullback", 3)
                result.pullback = True
            result.maturity = features.trend_maturity
            result.trend_strength = features.trend_strength
            if features.pending_external_bias is not TrendDirection.RANGING:
                result.reasons.append(
                    f"Pending external reversal: {features.pending_external_bias.value}"
                )

        session_trend = assess_session_trend(candles)
        score += session_trend.score_delta
        for reason in session_trend.reasons:
            if reason not in result.reasons:
                result.reasons.append(reason)
        if (
            session_trend.bias_hint is not TrendDirection.RANGING
            and result.direction is TrendDirection.RANGING
        ):
            result.direction = session_trend.bias_hint
        if session_trend.expansion_vs_asia:
            result.expansion = True
            if result.maturity == "developing":
                result.maturity = "expanding"
        if session_trend.compression_in_asia:
            result.compression = True

        result.score = clamp_score(score, max_score)
        return result

    @staticmethod
    def _apply_structure_relations(
        result: TrendAnalysis,
        features: MarketFeatures | None,
        rules: dict,
    ) -> int:
        """Score HH/HL/LH/LL from the v1 snapshot; never from a raw ten-candle split."""

        if features is None or features.structure_snapshot is None:
            return 0

        score = 0
        snapshot = features.structure_snapshot
        seen: set[str] = set()
        for rel in snapshot.swing_relations:
            if rel.scope is not SwingScope.EXTERNAL:
                continue
            key = rel.relation.value
            if key in seen:
                continue
            if rel.relation is StructureRelation.HH:
                seen.add(key)
                result.higher_highs = True
                score += rules.get("higher_highs", 2)
                result.reasons.append("Higher highs detected")
            elif rel.relation is StructureRelation.HL:
                seen.add(key)
                result.higher_lows = True
                score += rules.get("higher_lows", 2)
                result.reasons.append("Higher lows detected")
            elif rel.relation is StructureRelation.LH:
                seen.add(key)
                score += rules.get("lower_highs", 2)
                result.reasons.append("Lower highs detected")
            elif rel.relation is StructureRelation.LL:
                seen.add(key)
                score += rules.get("lower_lows", 2)
                result.reasons.append("Lower lows detected")

        if features.internal_bias is not TrendDirection.RANGING:
            # Internal bias is informational only — must not overwrite external.
            result.reasons.append(
                f"Internal bias {features.internal_bias.value} "
                f"(external {features.external_bias.value})"
            )
        return score

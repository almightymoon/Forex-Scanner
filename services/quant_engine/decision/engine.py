"""
Decision Engine V2 — orchestrates independent analysis engines.

The engine DECIDES trades. AI only explains (see ai_service).
No engine calls another; this class aggregates all outputs.
"""

from typing import Optional

from shared.config.scoring_loader import get_v2_scoring_config
from shared.types.models import (
    Candle,
    IndicatorValues,
    MTFAlignment,
    NewsContext,
    SMCPattern,
    ScannerSignal,
    ScoreBreakdown,
    SignalDirection,
    Timeframe,
    TrendDirection,
    rating_from_score,
)

from services.quant_engine.features import FeatureExtractor, MarketFeatures
from services.quant_engine.liquidity.models import LiquiditySnapshot
from services.quant_engine.market_structure.detector import analyze_structure
from services.quant_engine.market_structure.models import StructureSnapshot
from services.quant_engine.swings.boundary import (
    SCAN_SWING_VERSION,
    ScanStructureInput,
    build_scan_structure,
)
from services.setup_intelligence import HistoricalSetupAnalyzer, SetupFingerprint
from services.quant_engine.confidence.output import EngineOutput
from services.quant_engine.decision.explainability import (
    build_detected_patterns,
    build_evidence_checklist,
    build_explainability_summary,
    build_score_deltas,
)
from services.quant_engine.fvg.engine import FairValueGapEngine
from services.quant_engine.liquidity.engine import LiquidityEngine
from services.quant_engine.market_structure.engine import MarketStructureEngine
from services.quant_engine.decision.models import MomentumAnalysis
from services.quant_engine.trend.models import TrendAnalysis
from services.quant_engine.decision.engines.momentum import MomentumEngine
from services.quant_engine.decision.engines.mtf import MultiTimeframeEngine
from services.quant_engine.decision.engines.news import NewsEngine
from services.quant_engine.order_blocks.engine import OrderBlockEngine
from services.quant_engine.decision.engines.risk import RiskEngine
from services.quant_engine.decision.session import current_session, session_weight
from services.quant_engine.decision.structure_policy import apply_structure_decision_policy
from services.quant_engine.pipeline import ANALYSIS_PIPELINE_VERSION
from services.quant_engine.smc_confluence import build_smc_context
from services.quant_engine.smc_confluence.models import ConfluenceBias
from services.quant_engine.trend.engine import TrendEngine
from services.quant_engine.decision.engines.volatility import VolatilityEngine
from swing_engine.models import DetectedSwing



def _format_structure_adjustment(payload: dict) -> str:
    """Human-readable summary of structure_policy for explainability.adjustments."""
    parts: list[str] = ["structure policy"]
    mult = payload.get("confidence_multiplier")
    if isinstance(mult, (int, float)) and mult != 1:
        parts.append(f"confidence ×{mult}")
    delta = payload.get("score_delta")
    if isinstance(delta, int) and delta != 0:
        parts.append(f"score {delta:+d}")
    if payload.get("force_neutral"):
        parts.append("forced neutral")
    reasons = [r for r in (payload.get("reasons") or []) if isinstance(r, str)]
    warnings = [w for w in (payload.get("warnings") or []) if isinstance(w, str)]
    detail = reasons or warnings
    if detail:
        parts.append("; ".join(detail[:3]))
    return " — ".join(parts)


class DecisionEngine:
    """Production-grade deterministic decision aggregator."""

    def __init__(self):
        cfg = get_v2_scoring_config()
        self._config = cfg
        self.trend_engine = TrendEngine(cfg)
        self.market_structure_engine = MarketStructureEngine(cfg)
        self.liquidity_engine = LiquidityEngine(cfg)
        self.order_block_engine = OrderBlockEngine(cfg)
        self.fvg_engine = FairValueGapEngine(cfg)
        self.momentum_engine = MomentumEngine(cfg)
        self.volatility_engine = VolatilityEngine(cfg)
        self.risk_engine = RiskEngine(cfg)
        self.news_engine = NewsEngine(cfg)
        self.mtf_engine = MultiTimeframeEngine(cfg)
        self._historical = HistoricalSetupAnalyzer()
        self._features = FeatureExtractor()

    def evaluate(
        self,
        symbol: str,
        timeframe: Timeframe,
        candles: list[Candle],
        indicators: IndicatorValues,
        smc_patterns: list[SMCPattern],
        mtf_trends: Optional[dict[str, TrendDirection]] = None,
        news: Optional[NewsContext] = None,
        confirmed_swings: Optional[list[DetectedSwing]] = None,
        structure_snapshot: Optional[StructureSnapshot] = None,
        structure_input: Optional[ScanStructureInput] = None,
        liquidity_snapshot: Optional[LiquiditySnapshot] = None,
    ) -> ScannerSignal:
        news_ctx = news or NewsContext()
        mtf_map = mtf_trends or {}

        if structure_input is not None:
            if structure_input.swing_version != SCAN_SWING_VERSION and (
                confirmed_swings is None and structure_snapshot is None
            ):
                # Explicit alternate version from ScanStructureInput is honored.
                pass
            swings = list(structure_input.confirmed_swings)
            snapshot = structure_input.structure_snapshot
            if snapshot is None:
                snapshot = analyze_structure(candles, swings)
        elif confirmed_swings is not None:
            swings = list(confirmed_swings)
            snapshot = structure_snapshot
            if snapshot is None:
                snapshot = analyze_structure(candles, swings)
        else:
            # Standalone evaluate entry: one canonical producer call.
            built = build_scan_structure(candles, version=SCAN_SWING_VERSION)
            swings = list(built.confirmed_swings)
            snapshot = (
                structure_snapshot
                if structure_snapshot is not None
                else built.structure_snapshot
            )

        features = self._features.extract(
            candles,
            indicators,
            smc_patterns,
            confirmed_swings=swings,
            structure_snapshot=snapshot,
            liquidity_snapshot=liquidity_snapshot,
        )

        if features.structure_snapshot is not None:
            structure_output = self.market_structure_engine.run_from_structure_snapshot(
                features.structure_snapshot,
                smc_patterns,
                candles=candles,
                features=features,
            )
        else:
            structure_output = self.market_structure_engine.run(
                smc_patterns, candles, features
            )

        liquidity_output = self.liquidity_engine.run(smc_patterns, candles, features)
        order_block_output = self.order_block_engine.run(smc_patterns, candles, features)
        fvg_output = self.fvg_engine.run(smc_patterns, candles, features)

        outputs: list[EngineOutput] = [
            self.trend_engine.run(candles, indicators, features),
            structure_output,
            liquidity_output,
            order_block_output,
            fvg_output,
            self.momentum_engine.run(len(candles), indicators),
            self.volatility_engine.run(candles, indicators),
            self.news_engine.run(news_ctx),
        ]

        trend_analysis = self.trend_engine.analyze(candles, indicators, features)
        primary_trend = trend_analysis.direction
        momentum_analysis = self.momentum_engine.analyze(indicators, primary_trend)
        sr_analysis = self.risk_engine.analyze_support_resistance(candles, indicators, primary_trend)
        vol_analysis = self.risk_engine.analyze_volume(candles, indicators)
        mtf_out = self.mtf_engine.run(mtf_map, primary_trend)
        outputs.append(mtf_out)

        direction = self._resolve_direction(outputs, primary_trend)
        structure_adj = apply_structure_decision_policy(
            features=features,
            patterns=smc_patterns,
            direction=direction,
            primary_trend=primary_trend,
            mtf_trends=mtf_map,
        )
        if structure_adj.force_neutral:
            direction = SignalDirection.NEUTRAL

        # Assemble SMC context from already-computed artifacts (no re-detection).
        smc_context = build_smc_context(
            symbol=symbol,
            timeframe=timeframe,
            candles=candles,
            features=features,
            structure_snapshot=features.structure_snapshot,
            liquidity_snapshot=features.liquidity_snapshot,
            patterns=smc_patterns,
            mtf_trends=mtf_map,
            fvg_output=fvg_output,
            order_block_output=order_block_output,
            proposed_direction=direction,
        )

        risk_out = self.risk_engine.run(
            candles, indicators, primary_trend, direction, features=features
        )
        outputs.append(risk_out)

        total = max(0, min(100, sum(o.score for o in outputs) + structure_adj.score_delta))
        score_v2 = {self._key(o.name): o.score for o in outputs}
        score_v2["structure_policy"] = structure_adj.score_delta
        warnings = [w for o in outputs for w in o.warnings]
        warnings.extend(structure_adj.warnings)
        if smc_context.dominant_bias is ConfluenceBias.MIXED:
            warnings.append("SMC context MIXED — conflicting confluence evidence")
        elif smc_context.dominant_bias is ConfluenceBias.UNDEFINED:
            warnings.append("SMC context UNDEFINED — insufficient structure confluence")
        if news_ctx.has_high_impact_soon and news_ctx.minutes_until_event and news_ctx.minutes_until_event <= 30:
            warnings.append("High-impact news may block this setup")

        session = current_session()
        confidence = self._compute_confidence(total, outputs, news_ctx, session)
        confidence = round(
            min(max(confidence * structure_adj.confidence_multiplier, 0.0), 1.0),
            3,
        )
        legacy_breakdown = self._legacy_breakdown(outputs)
        mtf_alignment = self._mtf_model(mtf_out, mtf_map)

        fingerprint = SetupFingerprint.from_signal(
            direction, primary_trend, smc_patterns, total,
        )
        # Historical evidence is informational only on the live decision path.
        # Confidence is NOT multiplied by in-window forward outcomes (those are
        # valid research stats but create in-sample optimism if applied live).
        historical = self._historical.analyze(
            symbol,
            timeframe,
            candles,
            fingerprint,
            as_of_index=len(candles) - 1,
            apply_confidence_adjustment=False,
        )

        entry, sl, tp1, tp2, tp3, rr = self.risk_engine.calculate_levels(
            candles, indicators, direction
        )
        risk_level = self.risk_engine.assess_risk(
            total, news_ctx, not any("spread" in w.lower() for w in warnings)
        )

        smc_reasons = (
            outputs[1].reasons + outputs[2].reasons
            + outputs[3].reasons + outputs[4].reasons
        )
        technical_reasons = outputs[0].reasons + outputs[5].reasons + risk_out.reasons

        trend_stub = trend_analysis
        momentum_stub = momentum_analysis
        detected = build_detected_patterns(smc_reasons, smc_patterns)
        deltas = build_score_deltas(
            trend_stub, momentum_stub, smc_reasons,
            sr_analysis, vol_analysis, mtf_out.score, mtf_out.metadata.get("aligned") == mtf_out.metadata.get("checked"),
            news_ctx, smc_patterns,
        )
        factors = [o.to_dict() for o in outputs]
        hist_dict = historical.to_dict() if historical.sample_size > 0 else None
        evidence = build_evidence_checklist(factors, smc_patterns, news_ctx, session, hist_dict)
        explainability = build_explainability_summary(
            total, confidence, factors, detected, deltas, session,
            evidence=evidence, historical=hist_dict,
        )
        if historical.confidence_adjustment:
            explainability.setdefault("adjustments", []).append(historical.confidence_adjustment)
        # Keep structured policy separately; adjustments list is string-only for UI safety.
        structure_payload = {"source": "structure_policy", **structure_adj.to_dict()}
        explainability["structure_policy"] = structure_payload
        explainability.setdefault("adjustments", []).append(
            _format_structure_adjustment(structure_payload)
        )
        explainability["setup_confluence"] = structure_adj.confluence.to_dict()
        explainability["smc_context"] = smc_context.to_dict()

        explanation = self._build_explanation(
            symbol, direction, total, confidence, session, outputs, warnings, historical,
            smc_context=smc_context,
        )

        market_features = features.to_dict()
        market_features["setup_confluence"] = structure_adj.confluence.to_dict()
        market_features["structure_decision_policy"] = structure_adj.to_dict()
        market_features["smc_context"] = smc_context.to_dict()
        market_features["pipeline_version"] = ANALYSIS_PIPELINE_VERSION
        market_features["swing_version"] = SCAN_SWING_VERSION
        market_features["algorithm_versions"] = {
            "pipeline": ANALYSIS_PIPELINE_VERSION,
            "swing": SCAN_SWING_VERSION,
            **smc_context.algorithm_versions.to_dict(),
        }

        return ScannerSignal(
            symbol=symbol,
            timeframe=timeframe,
            direction=direction,
            score=total,
            rating=rating_from_score(total),
            trend=primary_trend,
            risk_level=risk_level,
            score_breakdown=legacy_breakdown,
            technical_reasons=technical_reasons,
            smc_reasons=smc_reasons,
            news_impact=news_ctx,
            mtf_alignment=mtf_alignment,
            entry_zone_low=entry[0] if entry else None,
            entry_zone_high=entry[1] if entry else None,
            stop_loss=sl,
            take_profit_1=tp1,
            take_profit_2=tp2,
            take_profit_3=tp3,
            risk_reward=rr,
            ai_explanation=explanation,
            confidence=confidence,
            session=session,
            decision_factors=factors,
            detected_patterns=detected,
            score_deltas=deltas,
            explainability=explainability,
            engine_outputs=[o.to_dict() for o in outputs],
            score_breakdown_v2=score_v2,
            warnings=warnings,
            trade_type=self._trade_type(direction, outputs),
            expected_duration=self._expected_duration(session, historical),
            historical_evidence=historical.to_dict() if historical.sample_size > 0 else None,
            market_features=market_features,
        )

    def _resolve_direction(
        self, outputs: list[EngineOutput], primary_trend: TrendDirection
    ) -> SignalDirection:
        buy = sum(o.score for o in outputs if o.direction == "BUY")
        sell = sum(o.score for o in outputs if o.direction == "SELL")
        if buy > sell and primary_trend != TrendDirection.BEARISH:
            return SignalDirection.BUY
        if sell > buy and primary_trend != TrendDirection.BULLISH:
            return SignalDirection.SELL
        if primary_trend == TrendDirection.BULLISH:
            return SignalDirection.BUY
        if primary_trend == TrendDirection.BEARISH:
            return SignalDirection.SELL
        return SignalDirection.NEUTRAL

    def _compute_confidence(
        self, total: int, outputs: list[EngineOutput], news: NewsContext, session: str
    ) -> float:
        base = total / 100.0
        mtf = next((o for o in outputs if o.name == "Multi-Timeframe"), None)
        if mtf and mtf.confidence >= 0.9:
            base *= 1.08
        elif mtf and mtf.confidence < 0.5:
            base *= 0.92
        if any(o.name == "News" and o.metadata.get("blocked") for o in outputs):
            base *= 0.75
        base *= session_weight(session, self._config.session_weights)
        return round(min(max(base, 0.0), 1.0), 3)

    def _legacy_breakdown(self, outputs: list[EngineOutput]) -> ScoreBreakdown:
        by = {self._key(o.name): o for o in outputs}
        return ScoreBreakdown(
            trend=by.get("trend", EngineOutput("trend", 0, 20, 0)).score,
            smc=(
                by.get("market_structure", EngineOutput("", 0, 0, 0)).score
                + by.get("liquidity", EngineOutput("", 0, 0, 0)).score
                + by.get("order_block", EngineOutput("", 0, 0, 0)).score
                + by.get("fair_value_gap", EngineOutput("", 0, 0, 0)).score
            ),
            momentum=by.get("momentum", EngineOutput("", 0, 0, 0)).score,
            support_resistance=by.get("risk", EngineOutput("", 0, 0, 0)).score // 2,
            volume_volatility=by.get("volatility", EngineOutput("", 0, 0, 0)).score,
            mtf_alignment=by.get("multi_timeframe", EngineOutput("", 0, 0, 0)).score,
            news_risk=by.get("news", EngineOutput("", 0, 0, 0)).score,
        )

    def _mtf_model(self, mtf_out: EngineOutput, trends: dict) -> MTFAlignment:
        return MTFAlignment(
            M15=trends.get("M15"),
            H1=trends.get("H1"),
            H4=trends.get("H4"),
            D1=trends.get("D1"),
            aligned=mtf_out.metadata.get("aligned") == mtf_out.metadata.get("checked")
            and mtf_out.metadata.get("checked", 0) > 0,
            score=mtf_out.score,
        )

    def _key(self, name: str) -> str:
        return name.lower().replace(" ", "_").replace("-", "_")

    def _trade_type(self, direction: SignalDirection, outputs: list[EngineOutput]) -> str:
        smc_score = sum(
            o.score for o in outputs
            if o.name in ("Market Structure", "Order Block", "Fair Value Gap", "Liquidity")
        )
        if smc_score >= 15:
            return f"SMC {direction.value.upper()}"
        return f"Trend {direction.value.upper()}"

    def _expected_duration(self, session: str, historical=None) -> str:
        if historical and historical.sample_size > 0 and historical.avg_duration_bars:
            hours = historical.avg_duration_bars
            return f"~{hours} hours (historical avg)"
        durations = {
            "london_ny_overlap": "2-6 hours",
            "london": "4-12 hours",
            "new_york": "4-8 hours",
            "asia": "8-16 hours",
        }
        return durations.get(session, "4-12 hours")

    def _build_explanation(
        self,
        symbol: str,
        direction: SignalDirection,
        score: int,
        confidence: float,
        session: str,
        outputs: list[EngineOutput],
        warnings: list[str],
        historical=None,
        smc_context=None,
    ) -> str:
        lines = [
            f"{symbol} — {direction.value.upper()} — {score}/100",
            f"Confidence: {confidence * 100:.0f}% · Session: {session}",
            "",
        ]
        if smc_context is not None:
            lines.append(
                f"SMC Context: {smc_context.dominant_bias.value} "
                f"({smc_context.confluence_strength.value}) · "
                f"evidence={smc_context.evidence_strength:.2f}"
            )
            for line in smc_context.explanations[:5]:
                lines.append(f"  {line}")
            lines.append("")
        for o in outputs:
            if o.reasons:
                lines.append(f"{o.name}: {o.reasons[0]}")
        if historical and historical.sample_size > 0:
            lines.append("")
            lines.append(
                f"Historical: {historical.sample_size} similar setups — "
                f"{historical.win_rate:.0f}% win rate, avg R:R {historical.avg_rr:.1f}"
            )
        if warnings:
            lines.append("")
            lines.append("Warnings:")
            for w in warnings:
                lines.append(f"• {w}")
        return "\n".join(lines)

"""SMC Confluence Engine v1 — assemble structure + liquidity + FVG + OB + MTF.

Does not instantiate SwingEngine or re-run Market Structure / Liquidity detectors
when snapshots are already provided.
"""

from __future__ import annotations

from typing import Any

from shared.types.models import Candle, SMCPattern, SignalDirection, Timeframe, TrendDirection

from services.quant_engine.confidence.output import EngineOutput
from services.quant_engine.features.types import MarketFeatures
from services.quant_engine.liquidity.models import (
    LIQUIDITY_ENGINE_VERSION,
    LiquiditySide,
    LiquiditySnapshot,
    SweepKind,
    SweepQuality,
)
from services.quant_engine.market_structure.confluence import assess_setup_confluence
from services.quant_engine.market_structure.models import StructureEventType, StructureSnapshot
from services.quant_engine.market_structure.trend_labels import (
    MarketTrendLabel,
    classify_market_trend,
)
from services.quant_engine.smc_confluence.models import (
    SMC_CONFLUENCE_ENGINE_VERSION,
    AlgorithmVersions,
    ConfluenceBias,
    ConfluenceStrength,
    ConflictItem,
    EvidenceItem,
    SMCContextSnapshot,
)
from services.quant_engine.swings.boundary import SCAN_SWING_VERSION


_HTF = ("D1", "H4", "H1")
_LTF = ("M15", "M5")


def _tf_weight(tf: str | None) -> float:
    if not tf:
        return 1.0
    key = tf.upper()
    return {"D1": 3.0, "H4": 2.5, "H1": 2.0, "M30": 1.5, "M15": 1.2, "M5": 1.0}.get(key, 1.0)


def _latest_event(snapshot: StructureSnapshot | None, event_type: StructureEventType):
    if snapshot is None:
        return None
    for event in reversed(snapshot.events):
        if event.event_type is event_type:
            return event.to_dict()
    return None


def _liquidity_context(liq: LiquiditySnapshot | None) -> dict[str, Any]:
    if liq is None:
        return {
            "active_highs": [],
            "active_lows": [],
            "recent_high_sweeps": [],
            "recent_low_sweeps": [],
            "active_count": 0,
            "sweep_count": 0,
        }
    highs = [p.to_dict() for p in liq.active_pools if p.side is LiquiditySide.SELL_SIDE]
    lows = [p.to_dict() for p in liq.active_pools if p.side is LiquiditySide.BUY_SIDE]
    hi_sw = [s.to_dict() for s in liq.recent_sweeps if s.kind is SweepKind.SWEEP_HIGH]
    lo_sw = [s.to_dict() for s in liq.recent_sweeps if s.kind is SweepKind.SWEEP_LOW]
    return {
        "active_highs": highs[:8],
        "active_lows": lows[:8],
        "recent_high_sweeps": hi_sw[-5:],
        "recent_low_sweeps": lo_sw[-5:],
        "active_count": len(liq.active_pools),
        "sweep_count": len(liq.recent_sweeps),
        "algorithm_version": liq.algorithm_version,
    }


def _pattern_context(
    patterns: list[SMCPattern],
    *,
    pattern_type: str,
    engine_out: EngineOutput | None,
    features: MarketFeatures | None,
) -> dict[str, Any]:
    matched = [p for p in patterns if p.pattern_type == pattern_type]
    bullish = [p for p in matched if p.direction is SignalDirection.BUY]
    bearish = [p for p in matched if p.direction is SignalDirection.SELL]
    ctx: dict[str, Any] = {
        "count": len(matched),
        "bullish_count": len(bullish),
        "bearish_count": len(bearish),
        "engine_score": engine_out.score if engine_out else 0,
        "engine_direction": engine_out.direction if engine_out else "NEUTRAL",
        "reasons": list(engine_out.reasons[:4]) if engine_out else [],
    }
    if pattern_type == "fvg" and features and features.best_fvg:
        ctx["best"] = {
            "gap_size": features.best_fvg.gap_size,
            "fill_pct": features.best_fvg.fill_pct,
            "quality": features.best_fvg.quality,
            "confluence": features.best_fvg.confluence,
        }
    if pattern_type == "order_block" and features and features.best_ob:
        ctx["best"] = {
            "overall": features.best_ob.overall,
            "freshness": features.best_ob.freshness,
            "mitigation": features.best_ob.mitigation,
            "reaction": features.best_ob.reaction,
        }
    return ctx


def _mtf_context(mtf_trends: dict[str, TrendDirection] | None) -> dict[str, Any]:
    trends = mtf_trends or {}
    return {
        "trends": {k: v.value for k, v in sorted(trends.items())},
        "htf": {k: trends[k].value for k in _HTF if k in trends},
        "ltf": {k: trends[k].value for k in _LTF if k in trends},
    }


def build_smc_context(
    *,
    symbol: str,
    timeframe: Timeframe | str,
    candles: list[Candle] | None = None,
    features: MarketFeatures | None = None,
    structure_snapshot: StructureSnapshot | None = None,
    liquidity_snapshot: LiquiditySnapshot | None = None,
    patterns: list[SMCPattern] | None = None,
    mtf_trends: dict[str, TrendDirection] | None = None,
    fvg_output: EngineOutput | None = None,
    order_block_output: EngineOutput | None = None,
    as_of_index: int | None = None,
    proposed_direction: SignalDirection | None = None,
) -> SMCContextSnapshot:
    """Build SMCContextSnapshot from precomputed artifacts (no detectors)."""

    patterns = patterns or []
    snap = structure_snapshot or (features.structure_snapshot if features else None)
    liq = liquidity_snapshot or (features.liquidity_snapshot if features else None)
    tf = timeframe.value if isinstance(timeframe, Timeframe) else str(timeframe)
    as_of = (
        as_of_index
        if as_of_index is not None
        else (len(candles) - 1 if candles else (snap.as_of_index if snap else -1))
    )
    ts = None
    if candles and 0 <= as_of < len(candles):
        ts = candles[as_of].timestamp.isoformat()

    trend_label = MarketTrendLabel.UNDEFINED
    regime = features.structure_regime if features else "ranging"
    external = features.external_bias if features else TrendDirection.RANGING
    pending = features.pending_external_bias if features else TrendDirection.RANGING
    if snap is not None:
        trend_label, assessment = classify_market_trend(snap)
        regime = assessment.regime.value
        external = snap.external_bias
        pending = snap.pending_external_bias
    elif features and features.structure_regime_assessment:
        # Fallback: features already classified
        raw = features.structure_regime_assessment.get("trend")
        if raw:
            try:
                trend_label = MarketTrendLabel(raw)
            except ValueError:
                pass

    bullish: list[EvidenceItem] = []
    bearish: list[EvidenceItem] = []
    conflicts: list[ConflictItem] = []

    # Structure evidence
    if external is TrendDirection.BULLISH:
        bullish.append(
            EvidenceItem("bullish", "structure", "External bias bullish", 2.0 * _tf_weight(tf), tf)
        )
    elif external is TrendDirection.BEARISH:
        bearish.append(
            EvidenceItem("bearish", "structure", "External bias bearish", 2.0 * _tf_weight(tf), tf)
        )

    if trend_label is MarketTrendLabel.BULLISH:
        bullish.append(EvidenceItem("bullish", "structure", "Product trend BULLISH", 1.5, tf))
    elif trend_label is MarketTrendLabel.BEARISH:
        bearish.append(EvidenceItem("bearish", "structure", "Product trend BEARISH", 1.5, tf))
    elif trend_label is MarketTrendLabel.UNDEFINED:
        conflicts.append(
            ConflictItem("Undefined structure trend", ("structure",), "Insufficient structure evidence")
        )

    last_bos = _latest_event(snap, StructureEventType.BOS)
    last_choch = _latest_event(snap, StructureEventType.CHOCH)
    if last_bos:
        side = "bullish" if last_bos.get("direction") == TrendDirection.BULLISH.value else "bearish"
        item = EvidenceItem(
            side,
            "structure",
            "Latest BOS",
            1.2,
            tf,
            {"event": last_bos.get("event_id")},
        )
        (bullish if side == "bullish" else bearish).append(item)
    if last_choch:
        conflicts.append(
            ConflictItem(
                "CHOCH pending/recent",
                ("structure",),
                f"Latest CHOCH direction={last_choch.get('direction')}",
            )
        )

    # Liquidity evidence — sell-side (lows) sweep = bullish; buy-side (highs) sweep = bearish
    liq_ctx = _liquidity_context(liq)
    if liq is not None:
        for sweep in liq.recent_sweeps:
            weight = 1.5
            if sweep.bias_quality is SweepQuality.CONTINUATION:
                weight = 1.8
            elif sweep.bias_quality is SweepQuality.STOP_HUNT:
                weight = 0.9
            meta = {
                "sweep_id": sweep.sweep_id,
                "grade": sweep.grade.value,
                "bias_quality": sweep.bias_quality.value,
                "pool_type": sweep.pool_type.value,
            }
            if sweep.kind is SweepKind.SWEEP_LOW:
                bullish.append(
                    EvidenceItem(
                        "bullish",
                        "liquidity",
                        f"Sell-side liquidity swept @ {sweep.level_price:.5f} ({sweep.grade.value})",
                        weight,
                        liq.timeframe,
                        meta,
                    )
                )
            elif sweep.kind is SweepKind.SWEEP_HIGH:
                bearish.append(
                    EvidenceItem(
                        "bearish",
                        "liquidity",
                        f"Buy-side liquidity swept @ {sweep.level_price:.5f} ({sweep.grade.value})",
                        weight,
                        liq.timeframe,
                        meta,
                    )
                )
        if liq_ctx["active_lows"] and external is TrendDirection.BULLISH:
            bullish.append(
                EvidenceItem(
                    "bullish",
                    "liquidity",
                    "Active sell-side liquidity (lows) with bullish bias",
                    0.8,
                    liq.timeframe,
                )
            )
        if liq_ctx["active_highs"] and external is TrendDirection.BEARISH:
            bearish.append(
                EvidenceItem(
                    "bearish",
                    "liquidity",
                    "Active buy-side liquidity (highs) with bearish bias",
                    0.8,
                    liq.timeframe,
                )
            )
        if liq_ctx["recent_low_sweeps"] and liq_ctx["recent_high_sweeps"]:
            conflicts.append(
                ConflictItem(
                    "Liquidity conflict",
                    ("liquidity",),
                    "Both high and low liquidity recently swept",
                )
            )

    # FVG / OB from patterns + engine outputs
    fvg_ctx = _pattern_context(patterns, pattern_type="fvg", engine_out=fvg_output, features=features)
    ob_ctx = _pattern_context(
        patterns, pattern_type="order_block", engine_out=order_block_output, features=features
    )
    if fvg_ctx["bullish_count"]:
        bullish.append(
            EvidenceItem("bullish", "fvg", f"Bullish FVG x{fvg_ctx['bullish_count']}", 1.0, tf)
        )
    if fvg_ctx["bearish_count"]:
        bearish.append(
            EvidenceItem("bearish", "fvg", f"Bearish FVG x{fvg_ctx['bearish_count']}", 1.0, tf)
        )
    if ob_ctx["bullish_count"]:
        bullish.append(
            EvidenceItem("bullish", "order_block", f"Bullish OB x{ob_ctx['bullish_count']}", 1.0, tf)
        )
    if ob_ctx["bearish_count"]:
        bearish.append(
            EvidenceItem("bearish", "order_block", f"Bearish OB x{ob_ctx['bearish_count']}", 1.0, tf)
        )
    if fvg_ctx["bullish_count"] and ob_ctx["bearish_count"]:
        conflicts.append(
            ConflictItem("FVG vs OB", ("fvg", "order_block"), "Bullish FVG with bearish order block")
        )
    if fvg_ctx["bearish_count"] and ob_ctx["bullish_count"]:
        conflicts.append(
            ConflictItem("FVG vs OB", ("fvg", "order_block"), "Bearish FVG with bullish order block")
        )

    # MTF
    mtf_ctx = _mtf_context(mtf_trends)
    htf_bull = htf_bear = ltf_bull = ltf_bear = 0
    for key, val in (mtf_trends or {}).items():
        w = _tf_weight(key)
        if val is TrendDirection.BULLISH:
            bullish.append(EvidenceItem("bullish", "mtf", f"{key} bullish", w, key))
            if key in _HTF:
                htf_bull += 1
            if key in _LTF:
                ltf_bull += 1
        elif val is TrendDirection.BEARISH:
            bearish.append(EvidenceItem("bearish", "mtf", f"{key} bearish", w, key))
            if key in _HTF:
                htf_bear += 1
            if key in _LTF:
                ltf_bear += 1
    if htf_bull and htf_bear:
        conflicts.append(ConflictItem("HTF mixed", ("mtf",), "Higher timeframes disagree"))
    if htf_bear and ltf_bull:
        conflicts.append(
            ConflictItem("HTF/LTF conflict", ("mtf",), "Bearish HTF vs bullish LTF")
        )
    if htf_bull and ltf_bear:
        conflicts.append(
            ConflictItem("HTF/LTF conflict", ("mtf",), "Bullish HTF vs bearish LTF")
        )

    b_score = sum(e.weight for e in bullish)
    s_score = sum(e.weight for e in bearish)
    total = b_score + s_score
    evidence_strength = min(1.0, total / 12.0) if total else 0.0

    # Dominant bias
    if trend_label is MarketTrendLabel.UNDEFINED and total < 2.0:
        dominant = ConfluenceBias.UNDEFINED
        strength = ConfluenceStrength.NONE
    elif conflicts and abs(b_score - s_score) < 1.5 and total >= 3.0:
        dominant = ConfluenceBias.MIXED
        strength = ConfluenceStrength.MODERATE if total >= 6 else ConfluenceStrength.WEAK
    elif b_score > s_score + 1.0:
        dominant = ConfluenceBias.BULLISH
        strength = (
            ConfluenceStrength.STRONG
            if b_score >= 8 and s_score < b_score * 0.45
            else ConfluenceStrength.MODERATE
            if b_score >= 4
            else ConfluenceStrength.WEAK
        )
    elif s_score > b_score + 1.0:
        dominant = ConfluenceBias.BEARISH
        strength = (
            ConfluenceStrength.STRONG
            if s_score >= 8 and b_score < s_score * 0.45
            else ConfluenceStrength.MODERATE
            if s_score >= 4
            else ConfluenceStrength.WEAK
        )
    elif total == 0:
        dominant = ConfluenceBias.UNDEFINED
        strength = ConfluenceStrength.NONE
    else:
        dominant = ConfluenceBias.NEUTRAL
        strength = ConfluenceStrength.WEAK

    setup = assess_setup_confluence(
        features=features,
        patterns=patterns,
        snapshot=snap,
        proposed_direction=proposed_direction,
    )

    explanations: list[str] = [
        f"Dominant bias: {dominant.value} ({strength.value})",
        f"Trend: {trend_label.value} · Regime: {regime}",
        f"Bullish evidence {b_score:.1f} vs bearish {s_score:.1f}",
    ]
    for e in bullish[:4]:
        explanations.append(f"+ {e.label}" + (f" [{e.source_timeframe}]" if e.source_timeframe else ""))
    for e in bearish[:4]:
        explanations.append(f"- {e.label}" + (f" [{e.source_timeframe}]" if e.source_timeframe else ""))
    for c in conflicts[:3]:
        explanations.append(f"! {c.label}: {c.detail}")
    explanations.append(f"Setup confluence score={setup.score:.2f} aligned={setup.aligned}")

    confidence = round(
        min(
            0.95,
            0.25
            + evidence_strength * 0.45
            + (0.15 if setup.aligned else 0.0)
            + (0.1 if strength is ConfluenceStrength.STRONG else 0.0)
            - (0.12 if dominant is ConfluenceBias.MIXED else 0.0)
            - (0.15 if dominant is ConfluenceBias.UNDEFINED else 0.0),
        ),
        3,
    )

    versions = AlgorithmVersions(
        smc_confluence_engine=SMC_CONFLUENCE_ENGINE_VERSION,
        swing_engine=SCAN_SWING_VERSION,
        liquidity_engine=(liq.algorithm_version if liq else LIQUIDITY_ENGINE_VERSION),
    )

    return SMCContextSnapshot(
        symbol=symbol,
        timeframe=tf,
        as_of_index=as_of,
        timestamp=ts,
        trend=trend_label.value,
        structure_regime=regime,
        external_bias=external.value,
        pending_external_bias=pending.value,
        last_bos=last_bos,
        last_choch=last_choch,
        liquidity_context=liq_ctx,
        fvg_context=fvg_ctx,
        order_block_context=ob_ctx,
        mtf_context=mtf_ctx,
        bullish_confluences=tuple(bullish),
        bearish_confluences=tuple(bearish),
        conflicts=tuple(conflicts),
        bullish_score=b_score,
        bearish_score=s_score,
        evidence_strength=evidence_strength,
        dominant_bias=dominant,
        confluence_strength=strength,
        confidence=confidence,
        explanations=tuple(explanations),
        setup_confluence=setup.to_dict(),
        algorithm_versions=versions,
    )


class SMCConfluenceEngine:
    """Thin orchestration facade."""

    version = SMC_CONFLUENCE_ENGINE_VERSION

    def analyze(self, **kwargs) -> SMCContextSnapshot:
        return build_smc_context(**kwargs)

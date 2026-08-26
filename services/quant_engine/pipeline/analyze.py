"""Canonical analysis pipeline — single path for live / replay / backtest.

All analytical consumers should call :func:`analyze_candle_window` rather than
re-implementing swings → structure → SMC → DecisionEngine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

from shared.types.models import (
    Candle,
    IndicatorValues,
    NewsContext,
    ScannerSignal,
    SMCPattern,
    Timeframe,
    TrendDirection,
)

from services.indicator_service.indicators import compute_all
from services.quant_engine.fvg.lifecycle import detect_fvg_zones
from services.quant_engine.fvg.models import FVGZoneSet
from services.quant_engine.liquidity.analyzer import analyze_liquidity
from services.quant_engine.liquidity.models import LiquiditySnapshot
from services.quant_engine.market_structure.detector import analyze_structure
from services.quant_engine.order_blocks.lifecycle import detect_order_block_zones
from services.quant_engine.order_blocks.models import OrderBlockZoneSet
from services.quant_engine.pipeline.mtf_context import resolve_mtf_trends, select_ranking_htf_trend
from services.quant_engine.swings.boundary import (
    SCAN_SWING_VERSION,
    ScanStructureInput,
    build_scan_structure,
    obtain_confirmed_swings,
)
from services.smc_service.smc import SMCEngine
from swing_engine.models import DetectedSwing

# 1.4.0 — zone ranking trend_alignment uses resolved causal HTF trend.
ANALYSIS_PIPELINE_VERSION = "1.4.0"


@dataclass(frozen=True)
class AnalysisBundle:
    """Pre-decision (and optional decision) artifacts for one candle window."""

    symbol: str
    timeframe: Timeframe
    candles: tuple[Candle, ...]
    indicators: IndicatorValues
    confirmed_swings: tuple[DetectedSwing, ...]
    structure_snapshot: Any
    structure_input: ScanStructureInput
    smc_patterns: tuple[SMCPattern, ...]
    liquidity_snapshot: LiquiditySnapshot | None
    fvg_zones: FVGZoneSet | None
    ob_zones: OrderBlockZoneSet | None
    mtf_trends: dict[str, TrendDirection]
    news: NewsContext
    signal: ScannerSignal | None
    pipeline_version: str = ANALYSIS_PIPELINE_VERSION
    swing_version: str = SCAN_SWING_VERSION
    metadata: dict[str, Any] = field(default_factory=dict)

    def analytical_fingerprint(self) -> dict[str, Any]:
        """Stable subset for live/replay/backtest equivalence comparisons."""
        sig = self.signal
        liq = self.liquidity_snapshot
        fvg = self.fvg_zones
        ob = self.ob_zones
        return {
            "pipeline_version": self.pipeline_version,
            "swing_version": self.swing_version,
            "as_of_index": len(self.candles) - 1,
            "structure_external_bias": (
                self.structure_snapshot.external_bias.value
                if self.structure_snapshot is not None
                else None
            ),
            "structure_event_count": (
                len(self.structure_snapshot.events) if self.structure_snapshot else 0
            ),
            "liquidity_active_count": len(liq.active_pools) if liq else 0,
            "liquidity_sweep_count": len(liq.recent_sweeps) if liq else 0,
            "fvg_zone_count": len(fvg.zones) if fvg else 0,
            "fvg_active_count": len(fvg.active) if fvg else 0,
            "ob_zone_count": len(ob.zones) if ob else 0,
            "ob_active_count": len(ob.active) if ob else 0,
            "ranked_fvg_ids": [
                p.metadata.get("zone_id")
                for p in self.smc_patterns
                if p.pattern_type == "fvg"
            ],
            "ranked_ob_ids": [
                p.metadata.get("zone_id")
                for p in self.smc_patterns
                if p.pattern_type == "order_block"
            ],
            "smc_pattern_types": sorted({p.pattern_type for p in self.smc_patterns}),
            "mtf_trends": {k: v.value for k, v in sorted(self.mtf_trends.items())},
            "ranking_htf_trend": (self.metadata or {}).get("ranking_htf_trend"),
            "ranking_htf_tf": (self.metadata or {}).get("ranking_htf_tf"),
            "direction": sig.direction.value if sig else None,
            "score": sig.score if sig else None,
            "confidence": sig.confidence if sig else None,
            "trend": sig.trend.value if sig else None,
            "stop_loss": sig.stop_loss if sig else None,
            "take_profit_1": sig.take_profit_1 if sig else None,
            "entry_zone_low": sig.entry_zone_low if sig else None,
            "entry_zone_high": sig.entry_zone_high if sig else None,
        }


def analyze_candle_window(
    symbol: str,
    timeframe: Timeframe,
    candles: list[Candle],
    *,
    mtf_trends: Optional[dict[str, TrendDirection]] = None,
    htf_bars: Optional[Mapping[str, list[Candle]]] = None,
    news: Optional[NewsContext] = None,
    decision_engine=None,
    smc_engine: SMCEngine | None = None,
    evaluate: bool = True,
    confirmed_swings: list[DetectedSwing] | None = None,
    structure_snapshot=None,
    liquidity_snapshot: LiquiditySnapshot | None = None,
) -> AnalysisBundle:
    """Run the canonical analytical path on a causal candle prefix.

    Order: indicators → swings → structure → liquidity (once) → FVG/OB zones
    → resolve MTF/HTF trends → SMC patterns (context-aware ranking) → DecisionEngine.
    Does not fetch market data or apply trade execution.

    Pass ``htf_bars`` and/or ``mtf_trends``. If ``mtf_trends`` is None, trends
    are resolved via the HTF causality contract (provider series + rollup fill).
    Zone ranking uses :func:`select_ranking_htf_trend` on that map.
    """
    if not candles:
        raise ValueError("candles must be non-empty")

    smc = smc_engine or SMCEngine()
    indicators = compute_all(candles, symbol, timeframe)

    if confirmed_swings is not None and structure_snapshot is not None:
        swings = list(confirmed_swings)
        snapshot = structure_snapshot
        structure_input = ScanStructureInput(
            candles=tuple(candles),
            confirmed_swings=tuple(swings),
            swing_version=SCAN_SWING_VERSION,
            structure_snapshot=snapshot,
        )
    else:
        structure_input = build_scan_structure(candles, version=SCAN_SWING_VERSION)
        swings = list(structure_input.confirmed_swings)
        snapshot = structure_input.structure_snapshot

    atr = float(indicators.atr_14 or 0.0)
    if atr <= 0 and len(candles) >= 2:
        atr = sum(c.high - c.low for c in candles[-14:]) / min(14, len(candles))

    liq = liquidity_snapshot
    if liq is None:
        liq = analyze_liquidity(
            candles,
            snapshot=snapshot,
            patterns=[],
            atr=atr,
            external_bias=snapshot.external_bias if snapshot else None,
            symbol=symbol,
            timeframe=timeframe,
        )

    fvg_zones = detect_fvg_zones(candles, symbol=symbol, timeframe=timeframe)
    ob_zones = detect_order_block_zones(candles, symbol=symbol, timeframe=timeframe)

    if mtf_trends is not None:
        mtf = dict(mtf_trends)
    else:
        mtf = resolve_mtf_trends(candles, bars_by_timeframe=htf_bars)

    ranking_htf, ranking_htf_tf = select_ranking_htf_trend(mtf, timeframe)

    patterns = smc.detect_all(
        candles,
        symbol,
        timeframe,
        confirmed_swings=swings,
        structure_snapshot=snapshot,
        liquidity_snapshot=liq,
        fvg_zones=fvg_zones,
        ob_zones=ob_zones,
        ranking_htf_trend=ranking_htf,
        ranking_htf_tf=ranking_htf_tf,
    )

    news_ctx = news if news is not None else NewsContext()

    signal: ScannerSignal | None = None
    if evaluate:
        if decision_engine is None:
            from services.quant_engine.decision.engine import DecisionEngine

            decision_engine = DecisionEngine()
        signal = decision_engine.evaluate(
            symbol=symbol,
            timeframe=timeframe,
            candles=candles,
            indicators=indicators,
            smc_patterns=patterns,
            mtf_trends=mtf,
            news=news_ctx,
            confirmed_swings=swings,
            structure_snapshot=snapshot,
            structure_input=structure_input,
            liquidity_snapshot=liq,
        )
        if signal.market_features is None:
            signal.market_features = {}
        signal.market_features.setdefault("pipeline_version", ANALYSIS_PIPELINE_VERSION)
        signal.market_features.setdefault("swing_version", SCAN_SWING_VERSION)
        signal.market_features.setdefault(
            "ranking_htf_trend", ranking_htf.value if ranking_htf else None
        )
        signal.market_features.setdefault("ranking_htf_tf", ranking_htf_tf)

    return AnalysisBundle(
        symbol=symbol,
        timeframe=timeframe,
        candles=tuple(candles),
        indicators=indicators,
        confirmed_swings=tuple(swings),
        structure_snapshot=snapshot,
        structure_input=structure_input,
        smc_patterns=tuple(patterns),
        liquidity_snapshot=liq,
        fvg_zones=fvg_zones,
        ob_zones=ob_zones,
        mtf_trends=mtf,
        news=news_ctx,
        signal=signal,
        pipeline_version=ANALYSIS_PIPELINE_VERSION,
        swing_version=SCAN_SWING_VERSION,
        metadata={
            "evaluate": evaluate,
            "ranking_htf_trend": ranking_htf.value if ranking_htf else None,
            "ranking_htf_tf": ranking_htf_tf,
        },
    )


__all__ = [
    "ANALYSIS_PIPELINE_VERSION",
    "AnalysisBundle",
    "analyze_candle_window",
    "analyze_structure",
    "obtain_confirmed_swings",
]

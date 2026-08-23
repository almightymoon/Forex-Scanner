"""Canonical analysis pipeline — single path for live / replay / backtest.

All analytical consumers should call :func:`analyze_candle_window` rather than
re-implementing swings → structure → SMC → DecisionEngine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

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
from services.quant_engine.market_structure.detector import analyze_structure
from services.quant_engine.swings.boundary import (
    SCAN_SWING_VERSION,
    ScanStructureInput,
    build_scan_structure,
    obtain_confirmed_swings,
)
from services.smc_service.smc import SMCEngine
from swing_engine.models import DetectedSwing

# Bump when the ordered stages or default versions change.
ANALYSIS_PIPELINE_VERSION = "1.0.0"


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
    mtf_trends: dict[str, TrendDirection]
    news: NewsContext
    signal: ScannerSignal | None
    pipeline_version: str = ANALYSIS_PIPELINE_VERSION
    swing_version: str = SCAN_SWING_VERSION
    metadata: dict[str, Any] = field(default_factory=dict)

    def analytical_fingerprint(self) -> dict[str, Any]:
        """Stable subset for replay/backtest equivalence comparisons."""
        sig = self.signal
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
            "smc_pattern_types": sorted({p.pattern_type for p in self.smc_patterns}),
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
    news: Optional[NewsContext] = None,
    decision_engine=None,
    smc_engine: SMCEngine | None = None,
    evaluate: bool = True,
    confirmed_swings: list[DetectedSwing] | None = None,
    structure_snapshot=None,
) -> AnalysisBundle:
    """Run the canonical analytical path on a causal candle prefix.

    Order: indicators → swings → structure → SMC patterns → DecisionEngine.
    Does not fetch market data or apply trade execution.
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

    patterns = smc.detect_all(
        candles,
        symbol,
        timeframe,
        confirmed_swings=swings,
        structure_snapshot=snapshot,
    )
    mtf = dict(mtf_trends or {})
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
        )
        if signal.market_features is None:
            signal.market_features = {}
        signal.market_features.setdefault("pipeline_version", ANALYSIS_PIPELINE_VERSION)
        signal.market_features.setdefault("swing_version", SCAN_SWING_VERSION)

    return AnalysisBundle(
        symbol=symbol,
        timeframe=timeframe,
        candles=tuple(candles),
        indicators=indicators,
        confirmed_swings=tuple(swings),
        structure_snapshot=snapshot,
        structure_input=structure_input,
        smc_patterns=tuple(patterns),
        mtf_trends=mtf,
        news=news_ctx,
        signal=signal,
        pipeline_version=ANALYSIS_PIPELINE_VERSION,
        swing_version=SCAN_SWING_VERSION,
        metadata={"evaluate": evaluate},
    )


# Re-export for callers that only need swings+structure without SMC.
__all__ = [
    "ANALYSIS_PIPELINE_VERSION",
    "AnalysisBundle",
    "analyze_candle_window",
    "analyze_structure",
    "obtain_confirmed_swings",
]

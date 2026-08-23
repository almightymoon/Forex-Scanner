"""Normalized market feature set — single source of truth for all engines."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from services.quant_engine.swing_analysis import MarketStructureState, TrendContext
from shared.types.models import TrendDirection

if TYPE_CHECKING:
    from services.quant_engine.liquidity.models import LiquidityMap
    from services.quant_engine.market_structure.models import StructureSnapshot


@dataclass
class OrderBlockFeatures:
    freshness: float = 0.0
    volume: float = 0.0
    reaction: float = 0.0
    mitigation: float = 0.0
    impulse: float = 0.0
    overall: float = 0.0


@dataclass
class FVGFeatures:
    gap_size: float = 0.0
    fill_pct: float = 0.0
    quality: str = "low"
    confluence: float = 0.0


@dataclass
class MarketFeatures:
    """Normalized features extracted once per scan — consumed by all engines."""

    trend_strength: float = 0.0
    trend_direction: TrendDirection = TrendDirection.RANGING
    trend_maturity: str = "developing"
    compression: bool = False
    expansion: bool = False
    pullback: bool = False

    swing_count: int = 0
    swing_strength_avg: float = 0.0
    structure: MarketStructureState | None = None
    trend_context: TrendContext | None = None

    bos_kind: str = "external"
    last_structure_event: str | None = None
    structure_continuation: bool = True

    # Market Structure Engine v1 fields (backward-compatible defaults).
    structure_snapshot: StructureSnapshot | None = None
    external_bias: TrendDirection = TrendDirection.RANGING
    pending_external_bias: TrendDirection = TrendDirection.RANGING
    internal_bias: TrendDirection = TrendDirection.RANGING
    pending_internal_bias: TrendDirection = TrendDirection.RANGING
    latest_external_high: float | None = None
    latest_external_low: float | None = None
    latest_internal_high: float | None = None
    latest_internal_low: float | None = None
    structural_sequence: list[str] = field(default_factory=list)
    structure_event_ids: list[str] = field(default_factory=list)
    latest_structure_event_id: str | None = None
    latest_bos_choch: dict[str, Any] | None = None
    structure_metadata: dict[str, Any] = field(default_factory=dict)
    structure_regime: str = "ranging"
    structure_regime_confidence: float = 0.0
    structure_regime_assessment: dict[str, Any] = field(default_factory=dict)

    liquidity_pools: list[str] = field(default_factory=list)
    session_tags: list[str] = field(default_factory=list)
    equal_highs: bool = False
    equal_lows: bool = False
    liquidity_sweep: bool = False
    liquidity_map: LiquidityMap | None = None

    best_ob: OrderBlockFeatures | None = None
    best_fvg: FVGFeatures | None = None
    ob_count: int = 0
    fvg_count: int = 0

    atr: float = 0.0
    adx: float = 0.0
    rsi: float = 50.0
    spread_proxy: float = 0.0
    session: str = "off_hours"
    volatility_regime: str = "normal"
    momentum_bias: float = 0.0

    def to_dict(self) -> dict:
        return {
            "trend_strength": round(self.trend_strength, 3),
            "trend_direction": self.trend_direction.value,
            "trend_maturity": self.trend_maturity,
            "swing_count": self.swing_count,
            "swing_strength_avg": round(self.swing_strength_avg, 1),
            "bos_kind": self.bos_kind,
            "last_structure_event": self.last_structure_event,
            "structure_continuation": self.structure_continuation,
            "external_bias": self.external_bias.value,
            "pending_external_bias": self.pending_external_bias.value,
            "internal_bias": self.internal_bias.value,
            "pending_internal_bias": self.pending_internal_bias.value,
            "latest_external_high": self.latest_external_high,
            "latest_external_low": self.latest_external_low,
            "latest_internal_high": self.latest_internal_high,
            "latest_internal_low": self.latest_internal_low,
            "structural_sequence": list(self.structural_sequence),
            "structure_event_ids": list(self.structure_event_ids),
            "latest_structure_event_id": self.latest_structure_event_id,
            "latest_bos_choch": self.latest_bos_choch,
            "structure_metadata": dict(sorted(self.structure_metadata.items())),
            "structure_regime": self.structure_regime,
            "structure_regime_confidence": round(self.structure_regime_confidence, 3),
            "structure_regime_assessment": self.structure_regime_assessment,
            "liquidity_pools": self.liquidity_pools,
            "liquidity_map": (
                self.liquidity_map.to_dict() if self.liquidity_map is not None else None
            ),
            "session": self.session,
            "ob_quality": round(self.best_ob.overall, 1) if self.best_ob else 0,
            "fvg_quality": self.best_fvg.quality if self.best_fvg else None,
            "atr": round(self.atr, 6),
            "adx": round(self.adx, 1),
            "volatility_regime": self.volatility_regime,
        }

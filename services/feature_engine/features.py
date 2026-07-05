"""Normalized market feature set — single source of truth for all engines."""

from dataclasses import dataclass, field

from services.scanner_service.swing_analysis import MarketStructureState, TrendContext
from shared.types.models import IndicatorValues, SMCPattern, TrendDirection


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

    liquidity_pools: list[str] = field(default_factory=list)
    session_tags: list[str] = field(default_factory=list)
    equal_highs: bool = False
    equal_lows: bool = False
    liquidity_sweep: bool = False

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
            "liquidity_pools": self.liquidity_pools,
            "session": self.session,
            "ob_quality": round(self.best_ob.overall, 1) if self.best_ob else 0,
            "fvg_quality": self.best_fvg.quality if self.best_fvg else None,
            "atr": round(self.atr, 6),
            "adx": round(self.adx, 1),
            "volatility_regime": self.volatility_regime,
        }

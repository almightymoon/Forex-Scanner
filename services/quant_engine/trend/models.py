"""Trend analysis result types."""

from dataclasses import dataclass, field

from shared.types.models import TrendDirection


@dataclass
class TrendAnalysis:
    direction: TrendDirection = TrendDirection.RANGING
    ema_aligned: bool = False
    adx_strong: bool = False
    higher_highs: bool = False
    higher_lows: bool = False
    price_above_vwap: bool = False
    compression: bool = False
    expansion: bool = False
    pullback: bool = False
    maturity: str = "developing"
    trend_strength: float = 0.0
    score: int = 0
    reasons: list[str] = field(default_factory=list)

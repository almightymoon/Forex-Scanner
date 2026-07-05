"""Analysis result types used by scoring engines."""

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

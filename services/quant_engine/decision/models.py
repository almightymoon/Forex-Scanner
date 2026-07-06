"""Analysis result types used by decision sub-engines."""

from dataclasses import dataclass, field


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

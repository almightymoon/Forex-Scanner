"""Centralized scanner / decision engine configuration."""

from dataclasses import dataclass, field
from functools import lru_cache


@dataclass(frozen=True)
class RuleWeight:
    points: int
    label: str = ""


@dataclass(frozen=True)
class CategoryConfig:
    max_points: int
    rules: dict[str, RuleWeight]


@dataclass(frozen=True)
class ScoringConfig:
    """Rule-based scoring — change weights here, not in engine code."""

    trend: CategoryConfig
    momentum: CategoryConfig
    smc: CategoryConfig
    risk_sr: CategoryConfig
    risk_volume: CategoryConfig
    mtf: CategoryConfig
    news: CategoryConfig
    session_weights: dict[str, float] = field(default_factory=dict)
    smc_trend_alignment_boost: float = 1.2
    adx_threshold: float = 25.0
    rsi_bullish_min: float = 50.0
    rsi_bullish_max: float = 70.0
    rsi_bearish_min: float = 30.0
    rsi_bearish_max: float = 50.0
    spread_warning: float = 0.0005
    min_alert_score: int = 80
    scan_interval_seconds: int = 60
    default_timeframes: tuple[str, ...] = ("M15", "H1", "H4")
    rating_elite: int = 90
    rating_strong: int = 80
    rating_good: int = 70
    rating_moderate: int = 60


DEFAULT_SCORING = ScoringConfig(
    trend=CategoryConfig(
        max_points=20,
        rules={
            "ema_alignment": RuleWeight(8, "EMA stack aligned"),
            "adx_strong": RuleWeight(5, "ADX above threshold"),
            "higher_highs": RuleWeight(3, "Higher highs"),
            "higher_lows": RuleWeight(2, "Higher lows"),
            "price_above_vwap": RuleWeight(2, "Price above VWAP"),
        },
    ),
    momentum=CategoryConfig(
        max_points=15,
        rules={
            "macd_histogram": RuleWeight(5, "MACD histogram aligned"),
            "rsi_in_zone": RuleWeight(5, "RSI in trend zone"),
            "atr_expansion": RuleWeight(5, "ATR volatility expansion"),
        },
    ),
    smc=CategoryConfig(
        max_points=25,
        rules={
            "bos": RuleWeight(5, "Break of structure"),
            "choch": RuleWeight(3, "Change of character"),
            "order_block": RuleWeight(7, "Order block"),
            "fvg": RuleWeight(4, "Fair value gap"),
            "liquidity_sweep": RuleWeight(6, "Liquidity sweep"),
            "breaker_block": RuleWeight(5, "Breaker block"),
            "equal_highs": RuleWeight(3, "Equal highs"),
            "equal_lows": RuleWeight(3, "Equal lows"),
        },
    ),
    risk_sr=CategoryConfig(
        max_points=10,
        rules={
            "near_support": RuleWeight(5, "Near support"),
            "near_resistance": RuleWeight(5, "Near resistance"),
            "fib_confluence": RuleWeight(3, "Fibonacci confluence"),
            "pivot_confirmed": RuleWeight(2, "Pivot confirmed"),
        },
    ),
    risk_volume=CategoryConfig(
        max_points=10,
        rules={
            "volume_above_avg": RuleWeight(4, "Volume above average"),
            "atr_expanding": RuleWeight(3, "ATR expanding"),
            "breakout_strength": RuleWeight(3, "Strong breakout candle"),
            "spread_penalty": RuleWeight(-5, "Elevated spread penalty"),
        },
    ),
    mtf=CategoryConfig(
        max_points=10,
        rules={
            "full_alignment": RuleWeight(10, "All timeframes aligned"),
            "partial_default": RuleWeight(5, "Partial MTF data"),
        },
    ),
    news=CategoryConfig(
        max_points=10,
        rules={
            "clear": RuleWeight(10, "No high-impact news"),
            "medium_impact": RuleWeight(5, "Medium impact event"),
            "high_impact_soon": RuleWeight(3, "High impact approaching"),
            "high_impact_imminent": RuleWeight(0, "High impact within 30 min"),
        },
    ),
    session_weights={
        "london": 1.05,
        "new_york": 1.05,
        "london_ny_overlap": 1.10,
        "asia": 0.95,
        "off_hours": 0.90,
    },
)


@dataclass(frozen=True)
class ScannerConfig:
    scoring: ScoringConfig = DEFAULT_SCORING
    min_candles: int = 50
    enable_event_bus: bool = True
    event_stream: str = "fxnav:scanner"


@lru_cache
def get_scanner_config() -> ScannerConfig:
    import os
    return ScannerConfig(
        enable_event_bus=os.getenv("ENABLE_EVENT_BUS", "true").lower() == "true",
    )

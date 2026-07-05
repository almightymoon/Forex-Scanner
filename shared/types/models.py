"""Shared domain types for FX Navigators Scanner."""

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class Timeframe(str, Enum):
    M1 = "M1"
    M5 = "M5"
    M15 = "M15"
    M30 = "M30"
    H1 = "H1"
    H4 = "H4"
    D1 = "D1"
    W1 = "W1"


class SignalDirection(str, Enum):
    BUY = "buy"
    SELL = "sell"
    NEUTRAL = "neutral"


class TrendDirection(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    RANGING = "ranging"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    EXTREME = "extreme"


class ConfidenceRating(str, Enum):
    IGNORE = "ignore"
    MODERATE = "moderate"
    GOOD = "good"
    STRONG = "strong"
    ELITE = "elite"


class NewsImpact(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SubscriptionPlan(str, Enum):
    GUEST = "guest"
    FREE = "free"
    PRO = "pro"
    ELITE = "elite"
    ADMIN = "admin"


def to_dict(obj: Any) -> Any:
    """Recursively convert dataclasses and enums to JSON-serializable dicts."""
    if isinstance(obj, Enum):
        return obj.value
    if hasattr(obj, "__dataclass_fields__"):
        return {k: to_dict(v) for k, v in asdict(obj).items()}
    if isinstance(obj, list):
        return [to_dict(i) for i in obj]
    if isinstance(obj, dict):
        return {k: to_dict(v) for k, v in obj.items()}
    if isinstance(obj, datetime):
        return obj.isoformat()
    return obj


@dataclass
class Candle:
    symbol: str
    timeframe: Timeframe
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int = 0
    tick_volume: int = 0
    spread: Optional[float] = None


@dataclass
class Tick:
    symbol: str
    timestamp: datetime
    bid: float
    ask: float
    volume: int = 0


@dataclass
class IndicatorValues:
    symbol: str
    timeframe: Timeframe
    timestamp: datetime
    ema_20: Optional[float] = None
    ema_50: Optional[float] = None
    ema_200: Optional[float] = None
    sma_20: Optional[float] = None
    rsi_14: Optional[float] = None
    macd_line: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_histogram: Optional[float] = None
    atr_14: Optional[float] = None
    adx_14: Optional[float] = None
    vwap: Optional[float] = None
    bb_upper: Optional[float] = None
    bb_middle: Optional[float] = None
    bb_lower: Optional[float] = None
    stoch_k: Optional[float] = None
    stoch_d: Optional[float] = None
    supertrend: Optional[float] = None
    supertrend_direction: Optional[SignalDirection] = None


@dataclass
class SMCPattern:
    pattern_type: str
    direction: SignalDirection
    price_high: Optional[float] = None
    price_low: Optional[float] = None
    strength: float = 0.0
    metadata: dict = field(default_factory=dict)


@dataclass
class ScoreBreakdown:
    trend: int = 0
    smc: int = 0
    momentum: int = 0
    support_resistance: int = 0
    volume_volatility: int = 0
    mtf_alignment: int = 0
    news_risk: int = 0

    @property
    def total(self) -> int:
        return (
            self.trend + self.smc + self.momentum + self.support_resistance
            + self.volume_volatility + self.mtf_alignment + self.news_risk
        )


@dataclass
class MTFAlignment:
    M15: Optional[TrendDirection] = None
    H1: Optional[TrendDirection] = None
    H4: Optional[TrendDirection] = None
    D1: Optional[TrendDirection] = None
    aligned: bool = False
    score: int = 0


@dataclass
class NewsContext:
    has_high_impact_soon: bool = False
    minutes_until_event: Optional[int] = None
    event_title: Optional[str] = None
    impact: NewsImpact = NewsImpact.LOW
    score: int = 10


@dataclass
class ScannerSignal:
    symbol: str
    timeframe: Timeframe
    direction: SignalDirection
    score: int
    rating: ConfidenceRating
    trend: TrendDirection
    risk_level: RiskLevel
    score_breakdown: ScoreBreakdown
    technical_reasons: list[str] = field(default_factory=list)
    smc_reasons: list[str] = field(default_factory=list)
    news_impact: Optional[NewsContext] = None
    mtf_alignment: Optional[MTFAlignment] = None
    entry_zone_low: Optional[float] = None
    entry_zone_high: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit_1: Optional[float] = None
    take_profit_2: Optional[float] = None
    take_profit_3: Optional[float] = None
    risk_reward: Optional[float] = None
    ai_explanation: Optional[str] = None
    confidence: float = 0.0
    session: Optional[str] = None
    decision_factors: list[dict] = field(default_factory=list)
    detected_patterns: list[dict] = field(default_factory=list)
    score_deltas: list[dict] = field(default_factory=list)
    explainability: Optional[dict] = None
    engine_outputs: list[dict] = field(default_factory=list)
    score_breakdown_v2: Optional[dict] = None
    warnings: list[str] = field(default_factory=list)
    trade_type: Optional[str] = None
    expected_duration: Optional[str] = None
    historical_evidence: Optional[dict] = None
    market_features: Optional[dict] = None
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class EconomicEvent:
    currency: str
    title: str
    impact: NewsImpact
    forecast: Optional[str] = None
    previous: Optional[str] = None
    actual: Optional[str] = None
    event_time: datetime = field(default_factory=datetime.utcnow)


def rating_from_score(score: int) -> ConfidenceRating:
    if score >= 90:
        return ConfidenceRating.ELITE
    if score >= 80:
        return ConfidenceRating.STRONG
    if score >= 70:
        return ConfidenceRating.GOOD
    if score >= 60:
        return ConfidenceRating.MODERATE
    return ConfidenceRating.IGNORE

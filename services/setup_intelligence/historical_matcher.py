"""Historical setup matching — Phase 2 intelligence layer."""

from dataclasses import dataclass, field

from services.indicator_service.indicators import compute_all
from services.scanner_service.swing_analysis import session_from_hour
from services.smc_service.smc import SMCEngine
from shared.types.models import Candle, SignalDirection, Timeframe, TrendDirection


@dataclass
class SetupFingerprint:
    direction: str
    trend: str
    patterns: frozenset[str]
    score_bucket: int

    @classmethod
    def from_signal(cls, direction: SignalDirection, trend: TrendDirection, patterns: list, score: int) -> "SetupFingerprint":
        types = frozenset(p.pattern_type for p in patterns)
        return cls(
            direction=direction.value,
            trend=trend.value,
            patterns=types,
            score_bucket=score // 10,
        )

    def similarity(self, other: "SetupFingerprint") -> float:
        if self.direction != other.direction or self.trend != other.trend:
            return 0.0
        if not self.patterns and not other.patterns:
            return 0.5
        union = self.patterns | other.patterns
        if not union:
            return 0.0
        overlap = len(self.patterns & other.patterns) / len(union)
        score_match = 1.0 if abs(self.score_bucket - other.score_bucket) <= 1 else 0.5
        return overlap * 0.7 + score_match * 0.3


@dataclass
class HistoricalEvidence:
    sample_size: int = 0
    win_rate: float = 0.0
    avg_rr: float = 0.0
    avg_duration_bars: int = 0
    similar_setups: list[str] = field(default_factory=list)
    best_session: str | None = None
    worst_session: str | None = None

    def to_dict(self) -> dict:
        return {
            "sample_size": self.sample_size,
            "win_rate": round(self.win_rate, 1),
            "avg_rr": round(self.avg_rr, 2),
            "avg_duration_bars": self.avg_duration_bars,
            "avg_duration_hours": round(self.avg_duration_bars, 0),
            "similar_setups": self.similar_setups,
            "best_session": self.best_session,
            "worst_session": self.worst_session,
        }


class HistoricalSetupAnalyzer:
    """
    Walks candle history to find similar setups and measure outcomes.
    Uses the same SMC detection — no duplicate decision logic.
    """

    def __init__(self, smc: SMCEngine | None = None):
        self.smc = smc or SMCEngine()

    def analyze(
        self,
        symbol: str,
        timeframe: Timeframe,
        candles: list[Candle],
        fingerprint: SetupFingerprint,
        min_similarity: float = 0.55,
        forward_bars: int = 12,
        step: int = 8,
    ) -> HistoricalEvidence:
        evidence = HistoricalEvidence()
        if len(candles) < 80:
            return evidence

        wins = losses = 0
        rr_vals: list[float] = []
        durations: list[int] = []
        session_stats: dict[str, dict[str, int]] = {}

        for i in range(60, len(candles) - forward_bars, step):
            window = candles[: i + 1]
            sub = window[-50:]
            patterns = self.smc.detect_all(sub, symbol, timeframe)
            ind = compute_all(window, symbol, timeframe)

            trend = TrendDirection.RANGING
            if ind.ema_20 and ind.ema_50:
                trend = TrendDirection.BULLISH if ind.ema_20 > ind.ema_50 else TrendDirection.BEARISH

            direction = SignalDirection.BUY if trend == TrendDirection.BULLISH else SignalDirection.SELL
            hist_fp = SetupFingerprint.from_signal(direction, trend, patterns, score=70)

            if fingerprint.similarity(hist_fp) < min_similarity:
                continue

            entry = window[-1].close
            atr = ind.atr_14 or entry * 0.001
            if fingerprint.direction == "buy":
                sl, tp = entry - atr * 1.5, entry + atr * 2
            else:
                sl, tp = entry + atr * 1.5, entry - atr * 2

            outcome = self._simulate_forward(candles[i + 1 : i + 1 + forward_bars], entry, sl, tp, fingerprint.direction)
            sess = session_from_hour(window[-1].timestamp.hour)
            session_stats.setdefault(sess, {"wins": 0, "total": 0})
            session_stats[sess]["total"] += 1
            if outcome == "win":
                wins += 1
                session_stats[sess]["wins"] += 1
                risk = abs(entry - sl)
                reward = abs(tp - entry)
                if risk > 0:
                    rr_vals.append(reward / risk)
                durations.append(forward_bars)
            elif outcome == "loss":
                losses += 1
                durations.append(forward_bars // 2)

        total = wins + losses
        evidence.sample_size = total
        if total == 0:
            return evidence

        evidence.win_rate = (wins / total) * 100
        evidence.avg_rr = sum(rr_vals) / len(rr_vals) if rr_vals else 1.5
        evidence.avg_duration_bars = int(sum(durations) / len(durations)) if durations else forward_bars
        evidence.similar_setups = sorted(fingerprint.patterns)

        if session_stats:
            rates = {
                s: (d["wins"] / d["total"]) * 100
                for s, d in session_stats.items()
                if d["total"] >= 3
            }
            if rates:
                evidence.best_session = max(rates, key=rates.get)
                evidence.worst_session = min(rates, key=rates.get)

        return evidence

    @staticmethod
    def _simulate_forward(bars: list[Candle], entry: float, sl: float, tp: float, direction: str) -> str:
        for bar in bars:
            if direction == "buy":
                if bar.low <= sl:
                    return "loss"
                if bar.high >= tp:
                    return "win"
            else:
                if bar.high >= sl:
                    return "loss"
                if bar.low <= tp:
                    return "win"
        return "loss"

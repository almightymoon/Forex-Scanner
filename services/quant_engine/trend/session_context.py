"""Session-aware trend context: Asia range vs London/NY expansion."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from shared.types.models import Candle, TrendDirection

from services.quant_engine.decision.session import current_session
from services.quant_engine.swing_analysis import session_from_hour


@dataclass(frozen=True)
class SessionTrendAssessment:
    session: str
    asia_range: float | None
    recent_range: float | None
    expansion_vs_asia: bool
    compression_in_asia: bool
    bias_hint: TrendDirection
    reasons: tuple[str, ...]
    score_delta: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "session": self.session,
            "asia_range": self.asia_range,
            "recent_range": self.recent_range,
            "expansion_vs_asia": self.expansion_vs_asia,
            "compression_in_asia": self.compression_in_asia,
            "bias_hint": self.bias_hint.value,
            "reasons": list(self.reasons),
            "score_delta": self.score_delta,
        }


def assess_session_trend(
    candles: list[Candle],
    *,
    lookback: int = 24,
) -> SessionTrendAssessment:
    """Compare current session behavior to the recent Asia range."""

    if len(candles) < 8:
        return SessionTrendAssessment(
            session=current_session(candles[-1].timestamp if candles else None),
            asia_range=None,
            recent_range=None,
            expansion_vs_asia=False,
            compression_in_asia=False,
            bias_hint=TrendDirection.RANGING,
            reasons=("Insufficient bars for session trend",),
            score_delta=0,
        )

    window = candles[-lookback:]
    asia = [c for c in window if session_from_hour(c.timestamp.hour) == "asia"]
    session = current_session(candles[-1].timestamp)
    reasons: list[str] = []
    score_delta = 0
    asia_range = None
    recent_range = max(c.high for c in window[-6:]) - min(c.low for c in window[-6:])
    expansion = False
    compression = False
    bias = TrendDirection.RANGING

    if asia:
        asia_high = max(c.high for c in asia)
        asia_low = min(c.low for c in asia)
        asia_range = asia_high - asia_low
        last = candles[-1]
        if asia_range > 0 and recent_range > asia_range * 1.25:
            expansion = True
            reasons.append("London/NY range expanding vs Asia")
            score_delta += 2
            if last.close > asia_high:
                bias = TrendDirection.BULLISH
                reasons.append("Close above Asia high — expansion bullish")
            elif last.close < asia_low:
                bias = TrendDirection.BEARISH
                reasons.append("Close below Asia low — expansion bearish")
        elif asia_range > 0 and recent_range < asia_range * 0.7:
            compression = True
            reasons.append("Price compressed inside Asia range")
            score_delta -= 1
        else:
            reasons.append("Session range similar to Asia")

        if session == "asia":
            compression = compression or (asia_range > 0 and recent_range <= asia_range)
            if compression:
                reasons.append("Asia session — favor mean-reversion / wait")
                score_delta -= 1
        elif session in ("london", "london_ny_overlap", "new_york") and expansion:
            reasons.append(f"{session} expansion window")
            score_delta += 1
    else:
        reasons.append("No Asia bars in lookback")

    return SessionTrendAssessment(
        session=session,
        asia_range=asia_range,
        recent_range=recent_range,
        expansion_vs_asia=expansion,
        compression_in_asia=compression,
        bias_hint=bias,
        reasons=tuple(reasons),
        score_delta=score_delta,
    )

"""Market structure event quality scoring — BOS/CHoCH dimensions.

Live path (default):
    ``allow_lookahead=False`` — follow-through is omitted / zeroed so scoring
    never inspects candles after the break index.

Offline / diagnostic path:
    ``allow_lookahead=True`` — restores the historical forward-candle
    follow-through dimension for retrospective analysis only.
"""

from __future__ import annotations

from dataclasses import dataclass

from shared.types.models import Candle, SMCPattern, SignalDirection


@dataclass
class StructureQuality:
    strength: float = 0.0
    volume: float = 0.0
    distance: float = 0.0
    follow_through: float = 0.0
    overall: int = 0
    lookahead_used: bool = False

    def to_dict(self) -> dict:
        stars = _stars
        return {
            "strength": round(self.strength, 2),
            "volume": round(self.volume, 2),
            "distance": round(self.distance, 2),
            "follow_through": round(self.follow_through, 2),
            "overall": self.overall,
            "lookahead_used": self.lookahead_used,
            "stars": {
                "strength": stars(self.strength),
                "volume": stars(self.volume),
                "distance": stars(self.distance),
                "follow_through": stars(self.follow_through),
            },
        }


def _stars(value: float) -> str:
    filled = int(max(0, min(1, value)) * 5)
    return "★" * filled + "☆" * (5 - filled)


def score_structure_event(
    pattern: SMCPattern,
    candles: list[Candle],
    atr: float = 0.0,
    *,
    allow_lookahead: bool = False,
    as_of_index: int | None = None,
) -> StructureQuality:
    """Score BOS/CHoCH on strength, volume, distance, and optional follow-through.

    Parameters
    ----------
    allow_lookahead:
        When False (default, live-safe), follow-through is not computed from
        future candles and does not contribute to overall.
    as_of_index:
        Inclusive last usable candle index. Defaults to ``len(candles) - 1``.
        Break / volume windows never read past this index.
    """
    q = StructureQuality()
    if not candles:
        return q

    end = len(candles) - 1 if as_of_index is None else int(as_of_index)
    end = min(max(-1, end), len(candles) - 1)
    if end < 0:
        return q
    prefix = candles[: end + 1]

    atr = atr or _atr_proxy(prefix)
    # Prefer explicit break_index from v1 metadata when present.
    raw_idx = pattern.metadata.get("break_index")
    if raw_idx is None:
        raw_idx = pattern.metadata.get("swing_index", len(prefix) - 1)
    idx = min(max(0, int(raw_idx)), end)

    swing_strength = pattern.metadata.get("swing_strength", pattern.strength)
    q.strength = min(1.0, float(swing_strength) / 100)

    break_candle = prefix[idx]
    vols = [c.volume for c in prefix[max(0, idx - 10) : idx] if c.volume]
    if vols and break_candle.volume:
        q.volume = min(1.0, break_candle.volume / (sum(vols) / len(vols)))
    else:
        q.volume = 0.5

    broken_level = pattern.price_high or pattern.price_low or break_candle.close
    displacement = abs(break_candle.close - broken_level)
    q.distance = min(1.0, displacement / (atr * 1.5)) if atr > 0 else 0.5

    if allow_lookahead:
        # Offline only: may inspect candles after the break within as_of window.
        forward = prefix[idx + 1 : idx + 4]
        if forward:
            if pattern.direction == SignalDirection.BUY:
                move = max(c.close for c in forward) - break_candle.close
            else:
                move = break_candle.close - min(c.close for c in forward)
            q.follow_through = min(1.0, move / (atr * 2)) if atr > 0 else 0.3
        else:
            q.follow_through = 0.3
        q.lookahead_used = True
        if pattern.pattern_type == "choch":
            q.overall = int(
                (
                    q.strength * 0.3
                    + q.volume * 0.2
                    + q.distance * 0.25
                    + q.follow_through * 0.25
                )
                * 100
            )
        else:
            q.overall = int(
                (
                    q.strength * 0.35
                    + q.volume * 0.2
                    + q.distance * 0.25
                    + q.follow_through * 0.2
                )
                * 100
            )
    else:
        # Live-safe: redistribute former follow-through weight across causal dims.
        q.follow_through = 0.0
        q.lookahead_used = False
        if pattern.pattern_type == "choch":
            q.overall = int(
                (q.strength * 0.40 + q.volume * 0.25 + q.distance * 0.35) * 100
            )
        else:
            q.overall = int(
                (q.strength * 0.45 + q.volume * 0.25 + q.distance * 0.30) * 100
            )

    return q


def quality_label(pattern: SMCPattern, quality: StructureQuality, bos_kind: str = "external") -> str:
    side = "Bullish" if pattern.direction == SignalDirection.BUY else "Bearish"
    event = pattern.pattern_type.upper()
    if pattern.pattern_type == "bos":
        event = f"{bos_kind.title()} BOS"
    s = quality.to_dict()["stars"]
    mode = "live" if not quality.lookahead_used else "offline"
    return (
        f"{side} {event} — Str {s['strength']} Vol {s['volume']} "
        f"Dist {s['distance']} Follow {s['follow_through']} · "
        f"Quality {quality.overall}/100 ({mode})"
    )


def _atr_proxy(candles: list[Candle]) -> float:
    if len(candles) < 2:
        return 0.0
    return sum(c.high - c.low for c in candles[-14:]) / min(14, len(candles))

"""Market structure event quality scoring — BOS/CHoCH dimensions."""

from dataclasses import dataclass

from shared.types.models import Candle, SMCPattern, SignalDirection


@dataclass
class StructureQuality:
    strength: float = 0.0
    volume: float = 0.0
    distance: float = 0.0
    follow_through: float = 0.0
    overall: int = 0

    def to_dict(self) -> dict:
        stars = _stars
        return {
            "strength": round(self.strength, 2),
            "volume": round(self.volume, 2),
            "distance": round(self.distance, 2),
            "follow_through": round(self.follow_through, 2),
            "overall": self.overall,
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
) -> StructureQuality:
    """Score BOS/CHoCH on strength, volume, distance, and follow-through."""
    q = StructureQuality()
    if not candles:
        return q

    atr = atr or _atr_proxy(candles)
    idx = pattern.metadata.get("swing_index", len(candles) - 1)
    idx = min(max(0, idx), len(candles) - 1)

    swing_strength = pattern.metadata.get("swing_strength", pattern.strength)
    q.strength = min(1.0, swing_strength / 100)

    break_candle = candles[idx]
    vols = [c.volume for c in candles[max(0, idx - 10) : idx] if c.volume]
    if vols and break_candle.volume:
        q.volume = min(1.0, break_candle.volume / (sum(vols) / len(vols)))
    else:
        q.volume = 0.5

    broken_level = pattern.price_high or pattern.price_low or break_candle.close
    displacement = abs(break_candle.close - broken_level)
    q.distance = min(1.0, displacement / (atr * 1.5)) if atr > 0 else 0.5

    forward = candles[idx + 1 : idx + 4]
    if forward:
        if pattern.direction == SignalDirection.BUY:
            move = max(c.close for c in forward) - break_candle.close
        else:
            move = break_candle.close - min(c.close for c in forward)
        q.follow_through = min(1.0, move / (atr * 2)) if atr > 0 else 0.3
    else:
        q.follow_through = 0.3

    if pattern.pattern_type == "choch":
        q.overall = int((q.strength * 0.3 + q.volume * 0.2 + q.distance * 0.25 + q.follow_through * 0.25) * 100)
    else:
        q.overall = int((q.strength * 0.35 + q.volume * 0.2 + q.distance * 0.25 + q.follow_through * 0.2) * 100)

    return q


def quality_label(pattern: SMCPattern, quality: StructureQuality, bos_kind: str = "external") -> str:
    side = "Bullish" if pattern.direction == SignalDirection.BUY else "Bearish"
    event = pattern.pattern_type.upper()
    if pattern.pattern_type == "bos":
        event = f"{bos_kind.title()} BOS"
    s = quality.to_dict()["stars"]
    return (
        f"{side} {event} — Str {s['strength']} Vol {s['volume']} "
        f"Dist {s['distance']} Follow {s['follow_through']} · Quality {quality.overall}/100"
    )


def _atr_proxy(candles: list[Candle]) -> float:
    if len(candles) < 2:
        return 0.0
    return sum(c.high - c.low for c in candles[-14:]) / min(14, len(candles))

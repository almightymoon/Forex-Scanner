"""Shared pattern scoring utilities — engines do not call each other."""

from shared.types.models import SMCPattern, SignalDirection

from .engine_output import EngineOutput, clamp_score, confidence_from_score


def filter_patterns(patterns: list[SMCPattern], types: set[str]) -> list[SMCPattern]:
    return [p for p in patterns if p.pattern_type in types]


def score_pattern_set(
    name: str,
    patterns: list[SMCPattern],
    allowed_types: set[str],
    max_score: int,
    rule_points: dict[str, int],
    labels: dict[str, str] | None = None,
) -> EngineOutput:
    labels = labels or {}
    score = 0
    reasons: list[str] = []
    seen: set[str] = set()
    buy_votes = 0
    sell_votes = 0

    for p in patterns:
        if p.pattern_type not in allowed_types or p.pattern_type in seen:
            continue
        seen.add(p.pattern_type)
        pts = rule_points.get(p.pattern_type, 2)
        score += pts
        label = labels.get(p.pattern_type, p.pattern_type.replace("_", " ").title())
        dir_label = "Bullish" if p.direction == SignalDirection.BUY else "Bearish"
        reasons.append(f"{dir_label} {label}")
        if p.direction == SignalDirection.BUY:
            buy_votes += pts
        elif p.direction == SignalDirection.SELL:
            sell_votes += pts

    score = clamp_score(score, max_score)
    direction = "NEUTRAL"
    if buy_votes > sell_votes:
        direction = "BUY"
    elif sell_votes > buy_votes:
        direction = "SELL"

    return EngineOutput(
        name=name,
        score=score,
        max_score=max_score,
        confidence=confidence_from_score(score, max_score),
        direction=direction,
        reasons=reasons,
        metadata={"pattern_count": len(seen)},
    )

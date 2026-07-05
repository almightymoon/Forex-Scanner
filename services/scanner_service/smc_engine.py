"""SMC pattern scoring engine — scores detected SMC patterns."""

from shared.types.models import SMCPattern, SignalDirection, TrendDirection

MAX_SMC = 25

WEIGHTS = {
    "bos": 5,
    "choch": 3,
    "order_block": 7,
    "fvg": 4,
    "liquidity_sweep": 6,
    "breaker_block": 5,
    "equal_highs": 3,
    "equal_lows": 3,
}


class SMCScoreEngine:
    def analyze(self, patterns: list[SMCPattern], trend: TrendDirection) -> tuple[int, list[str]]:
        score = 0
        reasons: list[str] = []
        seen: set[str] = set()

        # Priority order: liquidity → order block → FVG → structure
        priority = ["liquidity_sweep", "order_block", "fvg", "bos", "choch", "breaker_block"]

        ordered = sorted(
            patterns,
            key=lambda p: priority.index(p.pattern_type) if p.pattern_type in priority else 99,
        )

        for pattern in ordered:
            if pattern.pattern_type in seen:
                continue
            seen.add(pattern.pattern_type)

            w = WEIGHTS.get(pattern.pattern_type, 2)
            aligned = (
                (trend == TrendDirection.BULLISH and pattern.direction == SignalDirection.BUY)
                or (trend == TrendDirection.BEARISH and pattern.direction == SignalDirection.SELL)
            )
            if aligned:
                w = int(w * 1.2)

            score += w
            label = pattern.pattern_type.replace("_", " ").title()
            reasons.append(f"{label} detected ({pattern.direction.value})")

        return min(score, MAX_SMC), reasons

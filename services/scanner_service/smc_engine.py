"""SMC pattern scoring engine — scores detected SMC patterns."""

from shared.types.models import SMCPattern, TrendDirection

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

        for pattern in patterns:
            w = WEIGHTS.get(pattern.pattern_type, 2)
            score += w
            label = pattern.pattern_type.replace("_", " ").title()
            reasons.append(f"{label} detected ({pattern.direction.value})")

        return min(score, MAX_SMC), reasons

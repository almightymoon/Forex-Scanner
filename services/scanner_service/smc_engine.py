"""SMC pattern scoring — config-driven weights and priority."""

from shared.config.scanner import ScoringConfig, get_scanner_config
from shared.types.models import SMCPattern, SignalDirection, TrendDirection


class SMCScoreEngine:
    def __init__(self, config: ScoringConfig | None = None):
        self.config = config or get_scanner_config().scoring

    def analyze(self, patterns: list[SMCPattern], trend: TrendDirection) -> tuple[int, list[str]]:
        cfg = self.config
        score = 0
        reasons: list[str] = []
        seen: set[str] = set()

        priority = ["liquidity_sweep", "order_block", "fvg", "bos", "choch", "breaker_block"]
        ordered = sorted(
            patterns,
            key=lambda p: priority.index(p.pattern_type) if p.pattern_type in priority else 99,
        )

        for pattern in ordered:
            if pattern.pattern_type in seen:
                continue
            seen.add(pattern.pattern_type)

            rule = cfg.smc.rules.get(pattern.pattern_type)
            w = rule.points if rule else 2
            aligned = (
                (trend == TrendDirection.BULLISH and pattern.direction == SignalDirection.BUY)
                or (trend == TrendDirection.BEARISH and pattern.direction == SignalDirection.SELL)
            )
            if aligned:
                w = int(w * cfg.smc_trend_alignment_boost)

            score += w
            label = pattern.pattern_type.replace("_", " ").title()
            reasons.append(f"{label} detected ({pattern.direction.value})")

        return min(score, cfg.smc.max_points), reasons

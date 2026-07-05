"""Liquidity engine — sweeps, equal highs/lows, liquidity pools."""

from shared.config.scoring_loader import V2ScoringConfig, get_v2_scoring_config
from shared.types.models import SMCPattern

from .engine_output import EngineOutput
from .pattern_scoring import filter_patterns, score_pattern_set

_LIQUIDITY_TYPES = {"liquidity_sweep", "equal_highs", "equal_lows"}


class LiquidityEngine:
    def __init__(self, config: V2ScoringConfig | None = None):
        self.config = config or get_v2_scoring_config()

    def run(self, patterns: list[SMCPattern]) -> EngineOutput:
        weights = self.config.weights
        rules = self.config.rules.get("liquidity", {
            "liquidity_sweep": 6, "equal_highs": 3, "equal_lows": 3,
        })
        return score_pattern_set(
            "Liquidity",
            filter_patterns(patterns, _LIQUIDITY_TYPES),
            _LIQUIDITY_TYPES,
            weights.liquidity,
            rules,
        )

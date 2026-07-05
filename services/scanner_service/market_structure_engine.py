"""Market Structure engine — BOS, CHOCH, swing structure."""

from shared.config.scoring_loader import V2ScoringConfig, get_v2_scoring_config
from shared.types.models import SMCPattern

from .engine_output import EngineOutput
from .pattern_scoring import filter_patterns, score_pattern_set

_STRUCTURE_TYPES = {"bos", "choch"}


class MarketStructureEngine:
    def __init__(self, config: V2ScoringConfig | None = None):
        self.config = config or get_v2_scoring_config()

    def run(self, patterns: list[SMCPattern]) -> EngineOutput:
        weights = self.config.weights
        rules = self.config.rules.get("market_structure", {
            "bos": 8, "choch": 6,
        })
        filtered = filter_patterns(patterns, _STRUCTURE_TYPES)
        output = score_pattern_set(
            "Market Structure",
            filtered,
            _STRUCTURE_TYPES,
            weights.market_structure,
            rules,
        )
        for p in filtered:
            if p.strength >= 70:
                output.metadata.setdefault("high_strength", []).append(p.pattern_type)
        return output

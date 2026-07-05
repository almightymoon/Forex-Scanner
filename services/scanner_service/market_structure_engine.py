"""Market Structure engine — BOS, CHOCH, swing structure."""

from shared.config.scoring_loader import V2ScoringConfig, get_v2_scoring_config
from shared.types.models import Candle, SMCPattern, SignalDirection

from .engine_output import EngineOutput, clamp_score, confidence_from_score
from .pattern_scoring import filter_patterns
from .swing_analysis import classify_bos, find_swings

_STRUCTURE_TYPES = {"bos", "choch"}


class MarketStructureEngine:
    def __init__(self, config: V2ScoringConfig | None = None):
        self.config = config or get_v2_scoring_config()

    def run(self, patterns: list[SMCPattern], candles: list[Candle] | None = None) -> EngineOutput:
        weights = self.config.weights
        rules = self.config.rules.get("market_structure", {
            "bos": 8, "choch": 6, "internal_bos": 4, "external_bos": 6,
        })
        filtered = filter_patterns(patterns, _STRUCTURE_TYPES)
        score = 0
        reasons: list[str] = []
        buy_pts = sell_pts = 0
        high_strength: list[str] = []
        bos_kind = "external"

        price = candles[-1].close if candles else 0
        swing_highs, swing_lows = find_swings(candles or [])
        if candles and swing_highs and swing_lows:
            bos_kind = classify_bos(swing_highs, swing_lows, price)

        for p in filtered:
            pts = rules.get(p.pattern_type, 6)
            if p.pattern_type == "bos":
                pts = rules.get(f"{bos_kind}_bos", pts)
            strength_bonus = min(3, int(p.strength / 30))
            pts += strength_bonus
            score += pts

            label = p.pattern_type.upper()
            if p.pattern_type == "bos":
                label = f"{bos_kind.title()} BOS"
            reasons.append(f"{label} (strength {p.strength})")

            if p.strength >= 70:
                high_strength.append(p.pattern_type)
            if p.direction == SignalDirection.BUY:
                buy_pts += pts
            else:
                sell_pts += pts

        score = clamp_score(score, weights.market_structure)
        direction = "BUY" if buy_pts > sell_pts else "SELL" if sell_pts > buy_pts else "NEUTRAL"
        return EngineOutput(
            name="Market Structure",
            score=score,
            max_score=weights.market_structure,
            confidence=confidence_from_score(score, weights.market_structure),
            direction=direction,
            reasons=reasons,
            metadata={
                "high_strength": high_strength,
                "bos_classification": bos_kind,
                "swing_count": len(swing_highs) + len(swing_lows),
            },
        )

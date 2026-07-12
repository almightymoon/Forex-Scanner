"""Market Structure engine — BOS, CHOCH with quality scoring."""

from shared.config.scoring_loader import V2ScoringConfig, get_v2_scoring_config
from shared.types.models import Candle, SMCPattern, SignalDirection

from services.quant_engine.features.types import MarketFeatures

from services.quant_engine.confidence.output import EngineOutput, clamp_score, confidence_from_score
from services.quant_engine.decision.pattern_scoring import filter_patterns
from services.quant_engine.market_structure.scoring import quality_label, score_structure_event
from services.quant_engine.swing_analysis import classify_bos, find_swings

_STRUCTURE_TYPES = {"bos", "choch"}


class MarketStructureEngine:
    def __init__(self, config: V2ScoringConfig | None = None):
        self.config = config or get_v2_scoring_config()

    def run(
        self,
        patterns: list[SMCPattern],
        candles: list[Candle] | None = None,
        features: MarketFeatures | None = None,
    ) -> EngineOutput:
        weights = self.config.weights
        rules = self.config.rules.get("market_structure", {
            "bos": 8, "choch": 6, "internal_bos": 4, "external_bos": 6,
        })
        filtered = filter_patterns(patterns, _STRUCTURE_TYPES)
        score = 0
        reasons: list[str] = []
        buy_pts = sell_pts = 0
        high_strength: list[str] = []
        qualities: list[dict] = []
        bos_kind = "external"
        atr = features.atr if features else 0.0

        price = candles[-1].close if candles else 0
        swing_highs, swing_lows = [], []
        if features and features.structure:
            swing_highs = features.structure.swing_highs
            swing_lows = features.structure.swing_lows
            bos_kind = features.bos_kind
        elif candles:
            swing_highs, swing_lows = find_swings(candles)
            if swing_highs and swing_lows:
                bos_kind = classify_bos(swing_highs, swing_lows, price)

        for p in filtered:
            quality = score_structure_event(p, candles or [], atr)
            qualities.append({"type": p.pattern_type, **quality.to_dict()})

            base = rules.get(p.pattern_type, 6)
            if p.pattern_type == "bos":
                base = rules.get(f"{bos_kind}_bos", base)

            quality_factor = quality.overall / 100
            pts = int(base * (0.5 + quality_factor * 0.5))
            pts = max(2, min(base + 3, pts))
            score += pts

            reasons.append(quality_label(p, quality, bos_kind))

            if quality.overall >= 70:
                high_strength.append(p.pattern_type)
            if p.direction == SignalDirection.BUY:
                buy_pts += pts
            else:
                sell_pts += pts

        score = clamp_score(score, weights.market_structure)
        direction = "BUY" if buy_pts > sell_pts else "SELL" if sell_pts > buy_pts else "NEUTRAL"
        best_quality = max((q["overall"] for q in qualities), default=0)
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
                "swing_count": features.swing_count if features else len(swing_highs) + len(swing_lows),
                "continuation": features.structure_continuation if features else True,
                "last_event": features.last_structure_event if features else None,
                "qualities": qualities,
                "best_quality": best_quality,
            },
        )

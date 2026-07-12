"""Liquidity engine — sweeps, equal highs/lows, session liquidity."""

from shared.config.scoring_loader import V2ScoringConfig, get_v2_scoring_config
from shared.types.models import Candle, SMCPattern, SignalDirection

from services.quant_engine.features.types import MarketFeatures

from services.quant_engine.confidence.output import EngineOutput, clamp_score, confidence_from_score
from services.quant_engine.decision.pattern_scoring import filter_patterns
from services.quant_engine.swing_analysis import detect_session_liquidity

_LIQUIDITY_TYPES = {"liquidity_sweep", "equal_highs", "equal_lows"}


class LiquidityEngine:
    def __init__(self, config: V2ScoringConfig | None = None):
        self.config = config or get_v2_scoring_config()

    def run(
        self,
        patterns: list[SMCPattern],
        candles: list[Candle] | None = None,
        features: MarketFeatures | None = None,
    ) -> EngineOutput:
        weights = self.config.weights
        rules = self.config.rules.get("liquidity", {
            "liquidity_sweep": 6, "equal_highs": 3, "equal_lows": 3,
            "buy_side": 4, "sell_side": 4,
        })
        filtered = filter_patterns(patterns, _LIQUIDITY_TYPES)
        score = 0
        reasons: list[str] = []
        buy_pts = sell_pts = 0
        pools: list[str] = []

        for p in filtered:
            pts = rules.get(p.pattern_type, 3)
            if p.pattern_type == "liquidity_sweep":
                side = "buy_side" if p.direction == SignalDirection.BUY else "sell_side"
                pts += rules.get(side, 2)
                reasons.append(f"Liquidity sweep ({side.replace('_', ' ')})")
            elif p.pattern_type == "equal_highs":
                pts += rules.get("equal_highs", 3)
                reasons.append("Equal highs — sell-side liquidity pool")
                pools.append("equal_highs")
            elif p.pattern_type == "equal_lows":
                pts += rules.get("equal_lows", 3)
                reasons.append("Equal lows — buy-side liquidity pool")
                pools.append("equal_lows")
            score += pts
            if p.direction == SignalDirection.BUY:
                buy_pts += pts
            else:
                sell_pts += pts

        session_tags = features.session_tags if features else detect_session_liquidity(candles or [])
        pools = features.liquidity_pools if features else pools
        for tag in session_tags:
            if "sweep" in tag.lower():
                score += 2
            reasons.append(tag)

        score = clamp_score(score, weights.liquidity)
        direction = "BUY" if buy_pts > sell_pts else "SELL" if sell_pts > buy_pts else "NEUTRAL"
        return EngineOutput(
            name="Liquidity",
            score=score,
            max_score=weights.liquidity,
            confidence=confidence_from_score(score, weights.liquidity),
            direction=direction,
            reasons=reasons,
            metadata={"liquidity_pools": pools, "session_tags": session_tags},
        )

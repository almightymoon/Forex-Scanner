"""Order Block engine — quality-scored bullish/bearish OB detection."""

from shared.config.scoring_loader import V2ScoringConfig, get_v2_scoring_config
from shared.types.models import Candle, SMCPattern, SignalDirection

from services.quant_engine.features.types import MarketFeatures

from services.quant_engine.confidence.output import EngineOutput, clamp_score, confidence_from_score
from services.quant_engine.decision.pattern_scoring import filter_patterns


class OrderBlockEngine:
    def __init__(self, config: V2ScoringConfig | None = None):
        self.config = config or get_v2_scoring_config()

    def run(
        self,
        patterns: list[SMCPattern],
        candles: list[Candle] | None = None,
        features: MarketFeatures | None = None,
    ) -> EngineOutput:
        weights = self.config.weights
        rules = self.config.rules.get("order_block", {"bullish_ob": 6, "bearish_ob": 6, "fresh_ob": 4})
        obs = filter_patterns(patterns, {"order_block"})
        score = 0
        reasons: list[str] = []
        buy_pts = sell_pts = 0
        qualities: list[dict] = []

        for p in obs[-3:]:
            if features and features.best_ob and p == obs[-1]:
                q = self._quality_from_features(p, features.best_ob)
            else:
                q = self._quality_score(p, candles or [], rules)
            score += q["points"]
            qualities.append(q)
            reasons.append(q["label"])
            if p.direction == SignalDirection.BUY:
                buy_pts += q["points"]
            else:
                sell_pts += q["points"]

        score = clamp_score(score, weights.order_block)
        direction = "BUY" if buy_pts > sell_pts else "SELL" if sell_pts > buy_pts else "NEUTRAL"
        return EngineOutput(
            name="Order Block",
            score=score,
            max_score=weights.order_block,
            confidence=confidence_from_score(score, weights.order_block),
            direction=direction,
            reasons=reasons,
            metadata={"count": len(obs), "qualities": qualities, "best_quality": qualities[-1]["quality"] if qualities else 0},
        )

    def _quality_from_features(self, p: SMCPattern, ob) -> dict:
        side = "Bullish" if p.direction == SignalDirection.BUY else "Bearish"
        stars = lambda v: "★" * int(v * 5) + "☆" * (5 - int(v * 5))
        overall = int(ob.overall)
        return {
            "points": min(10, overall // 10),
            "quality": overall,
            "fresh": ob.freshness > 0.5,
            "mitigated": ob.mitigation < 0.5,
            "label": (
                f"{side} OB — Fresh {stars(ob.freshness)} Vol {stars(ob.volume)} "
                f"Reaction {stars(ob.reaction)} Mit {stars(ob.mitigation)} "
                f"Impulse {stars(ob.impulse)} · Overall {overall}/100"
            ),
        }

    def _quality_score(self, p: SMCPattern, candles: list[Candle], rules: dict) -> dict:
        idx = p.metadata.get("index", len(candles) - 1)
        bars_since = max(0, len(candles) - 1 - idx) if candles else 99
        fresh = bars_since <= 8
        mitigated = self._is_mitigated(p, candles, idx)
        impulse = p.metadata.get("impulse_ratio", 1.5)
        volume_score = self._volume_score(candles, idx)
        reaction = self._reaction_score(p, candles, idx)

        base = rules.get("bullish_ob" if p.direction == SignalDirection.BUY else "bearish_ob", 6)
        points = base // 2
        tags: list[str] = []

        if fresh and not mitigated:
            points += rules.get("fresh_ob", 4)
            tags.append("fresh")
        elif mitigated:
            points += 1
            tags.append("mitigated")
        if impulse >= 1.8:
            points += 2
            tags.append("strong impulse")
        if volume_score >= 0.6:
            points += 1
            tags.append("volume confirmed")
        if reaction >= 0.5:
            points += 2
            tags.append("quality reaction")

        side = "Bullish" if p.direction == SignalDirection.BUY else "Bearish"
        quality_pct = min(100, int((points / (base + rules.get("fresh_ob", 4))) * 100))
        tag_str = f" ({', '.join(tags)})" if tags else ""
        return {
            "points": points,
            "quality": quality_pct,
            "fresh": fresh,
            "mitigated": mitigated,
            "label": f"{side} Order Block{tag_str} — quality {quality_pct}/100",
        }

    @staticmethod
    def _is_mitigated(p: SMCPattern, candles: list[Candle], idx: int) -> bool:
        if not candles or idx >= len(candles):
            return False
        ob_low = p.price_low or candles[idx].low
        ob_high = p.price_high or candles[idx].high
        for c in candles[idx + 1 :]:
            if c.low <= ob_high and c.high >= ob_low:
                return True
        return False

    @staticmethod
    def _volume_score(candles: list[Candle], idx: int) -> float:
        if not candles or idx >= len(candles):
            return 0.0
        vols = [c.volume for c in candles[max(0, idx - 10) : idx] if c.volume]
        if not vols or not candles[idx].volume:
            return 0.5
        avg = sum(vols) / len(vols)
        return min(1.0, candles[idx].volume / avg) if avg else 0.5

    @staticmethod
    def _reaction_score(p: SMCPattern, candles: list[Candle], idx: int) -> float:
        if not candles or idx + 3 >= len(candles):
            return 0.0
        entry = candles[idx + 1].close
        if p.direction == SignalDirection.BUY:
            move = max(c.high for c in candles[idx + 1 : idx + 4]) - entry
        else:
            move = entry - min(c.low for c in candles[idx + 1 : idx + 4])
        atr_proxy = abs(candles[idx].high - candles[idx].low) or 0.0001
        return min(1.0, move / (atr_proxy * 2))

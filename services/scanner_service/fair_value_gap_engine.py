"""Fair Value Gap engine — gap size, fill %, quality, confluence."""

from shared.config.scoring_loader import V2ScoringConfig, get_v2_scoring_config
from shared.types.models import Candle, SMCPattern, SignalDirection

from .engine_output import EngineOutput, clamp_score, confidence_from_score
from .pattern_scoring import filter_patterns


class FairValueGapEngine:
    def __init__(self, config: V2ScoringConfig | None = None):
        self.config = config or get_v2_scoring_config()

    def run(self, patterns: list[SMCPattern], candles: list[Candle] | None = None) -> EngineOutput:
        weights = self.config.weights
        rules = self.config.rules.get("fair_value_gap", {
            "bullish_fvg": 5, "bearish_fvg": 5, "filled": 2,
        })
        fvgs = filter_patterns(patterns, {"fvg"})
        score = 0
        reasons: list[str] = []
        buy_pts = sell_pts = 0
        gap_details: list[dict] = []

        for p in fvgs:
            detail = self._analyze_gap(p, candles or [], rules)
            score += detail["points"]
            gap_details.append(detail)
            reasons.append(detail["label"])
            if p.direction == SignalDirection.BUY:
                buy_pts += detail["points"]
            else:
                sell_pts += detail["points"]

        score = clamp_score(score, weights.fair_value_gap)
        direction = "BUY" if buy_pts > sell_pts else "SELL" if sell_pts > buy_pts else "NEUTRAL"
        return EngineOutput(
            name="Fair Value Gap",
            score=score,
            max_score=weights.fair_value_gap,
            confidence=confidence_from_score(score, weights.fair_value_gap),
            direction=direction,
            reasons=reasons,
            metadata={"gap_count": len(fvgs), "gaps": gap_details},
        )

    def _analyze_gap(self, p: SMCPattern, candles: list[Candle], rules: dict) -> dict:
        gap_low = p.price_low or 0
        gap_high = p.price_high or 0
        gap_size = p.metadata.get("gap_size") or max(gap_high - gap_low, 0)
        fill_pct = self._fill_percentage(p, candles)
        unfilled = fill_pct < 50

        base = rules.get("bullish_fvg" if p.direction == SignalDirection.BUY else "bearish_fvg", 5)
        points = base // 2
        if unfilled:
            points += base // 2 + 1
        elif fill_pct < 80:
            points += rules.get("filled", 2)
        if gap_size > 0:
            atr_proxy = (candles[-1].high - candles[-1].low) if candles else gap_size
            if atr_proxy and gap_size >= atr_proxy * 0.3:
                points += 1

        side = "Bullish" if p.direction == SignalDirection.BUY else "Bearish"
        quality = "high" if unfilled and gap_size > 0 else "moderate" if fill_pct < 80 else "low"
        label = (
            f"{side} FVG — gap {gap_size:.5f}, {fill_pct:.0f}% filled, {quality} quality"
        )
        return {
            "points": points,
            "gap_size": gap_size,
            "fill_pct": fill_pct,
            "quality": quality,
            "label": label,
        }

    @staticmethod
    def _fill_percentage(p: SMCPattern, candles: list[Candle]) -> float:
        gap_low = p.price_low
        gap_high = p.price_high
        if not gap_low or not gap_high or not candles:
            return 0.0
        gap_size = gap_high - gap_low
        if gap_size <= 0:
            return 100.0
        filled = 0.0
        for c in candles[-15:]:
            overlap_low = max(gap_low, c.low)
            overlap_high = min(gap_high, c.high)
            if overlap_high > overlap_low:
                filled = max(filled, overlap_high - overlap_low)
        return min(100.0, (filled / gap_size) * 100)

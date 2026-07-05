"""Extract normalized market features from candles, indicators, and patterns."""

from services.feature_engine.features import FVGFeatures, MarketFeatures, OrderBlockFeatures
from services.scanner_service.session import current_session
from services.scanner_service.swing_analysis import (
    analyze_market_structure,
    analyze_trend_context,
    detect_session_liquidity,
)
from shared.types.models import Candle, IndicatorValues, SMCPattern, SignalDirection


class FeatureExtractor:
    """Single pass feature extraction — all engines consume this output."""

    def extract(
        self,
        candles: list[Candle],
        indicators: IndicatorValues,
        patterns: list[SMCPattern],
    ) -> MarketFeatures:
        features = MarketFeatures()
        if not candles:
            return features

        ctx = analyze_trend_context(candles, indicators.ema_20, indicators.ema_50)
        structure = ctx.structure or analyze_market_structure(candles)

        features.trend_context = ctx
        features.structure = structure
        features.trend_strength = ctx.strength
        features.trend_direction = ctx.direction
        features.trend_maturity = ctx.maturity
        features.compression = ctx.compression
        features.expansion = ctx.expansion
        features.pullback = ctx.pullback

        features.swing_count = len(structure.swings)
        features.swing_strength_avg = structure.swing_strength_avg
        features.bos_kind = structure.bos_kind
        features.last_structure_event = structure.last_event
        features.structure_continuation = structure.continuation

        features.session = current_session(candles[-1].timestamp)
        features.session_tags = detect_session_liquidity(candles)

        features.atr = indicators.atr_14 or self._atr_proxy(candles)
        features.adx = indicators.adx_14 or 0.0
        features.rsi = indicators.rsi_14 or 50.0
        features.spread_proxy = (candles[-1].high - candles[-1].low) / max(candles[-1].close, 1e-8)

        if features.atr and len(candles) >= 20:
            recent_ranges = [c.high - c.low for c in candles[-20:]]
            avg = sum(recent_ranges) / len(recent_ranges)
            if avg < features.atr * 0.7:
                features.volatility_regime = "compressed"
            elif avg > features.atr * 1.3:
                features.volatility_regime = "expanded"
            else:
                features.volatility_regime = "normal"

        if indicators.macd_histogram is not None:
            features.momentum_bias = max(-1.0, min(1.0, indicators.macd_histogram * 10))
        elif indicators.rsi_14:
            features.momentum_bias = (indicators.rsi_14 - 50) / 50

        for p in patterns:
            if p.pattern_type == "equal_highs":
                features.equal_highs = True
                features.liquidity_pools.append("equal_highs")
            elif p.pattern_type == "equal_lows":
                features.equal_lows = True
                features.liquidity_pools.append("equal_lows")
            elif p.pattern_type == "liquidity_sweep":
                features.liquidity_sweep = True

        obs = [p for p in patterns if p.pattern_type == "order_block"]
        features.ob_count = len(obs)
        if obs:
            features.best_ob = self._best_ob(obs[-1], candles)

        fvgs = [p for p in patterns if p.pattern_type == "fvg"]
        features.fvg_count = len(fvgs)
        if fvgs:
            features.best_fvg = self._best_fvg(fvgs[-1], candles, features.atr)

        return features

    def _best_ob(self, p: SMCPattern, candles: list[Candle]) -> OrderBlockFeatures:
        idx = p.metadata.get("index", len(candles) - 1)
        bars_since = max(0, len(candles) - 1 - idx) if candles else 99
        fresh = 1.0 if bars_since <= 8 else max(0.0, 1.0 - bars_since / 30)
        mitigated = self._ob_mitigated(p, candles, idx)
        mitigation = 0.0 if mitigated else 1.0
        impulse = min(1.0, p.metadata.get("impulse_ratio", 1.0) / 2.0)
        volume = self._volume_score(candles, idx)
        reaction = self._reaction_score(p, candles, idx)

        overall = (fresh * 25 + volume * 20 + reaction * 25 + mitigation * 15 + impulse * 15)
        return OrderBlockFeatures(
            freshness=fresh,
            volume=volume,
            reaction=reaction,
            mitigation=mitigation,
            impulse=impulse,
            overall=overall,
        )

    def _best_fvg(self, p: SMCPattern, candles: list[Candle], atr: float) -> FVGFeatures:
        gap_low = p.price_low or 0
        gap_high = p.price_high or 0
        gap_size = p.metadata.get("gap_size") or max(gap_high - gap_low, 0)
        fill_pct = self._fvg_fill(p, candles)
        unfilled = fill_pct < 50
        size_score = min(1.0, gap_size / (atr * 0.5)) if atr and gap_size else 0.5
        quality = "high" if unfilled and size_score >= 0.6 else "moderate" if fill_pct < 80 else "low"
        confluence = size_score * (1.0 - fill_pct / 100)
        return FVGFeatures(gap_size=gap_size, fill_pct=fill_pct, quality=quality, confluence=confluence)

    @staticmethod
    def _atr_proxy(candles: list[Candle]) -> float:
        if len(candles) < 2:
            return 0.0
        return sum(c.high - c.low for c in candles[-14:]) / min(14, len(candles))

    @staticmethod
    def _ob_mitigated(p: SMCPattern, candles: list[Candle], idx: int) -> bool:
        if not candles or idx >= len(candles):
            return False
        ob_low = p.price_low or candles[idx].low
        ob_high = p.price_high or candles[idx].high
        return any(c.low <= ob_high and c.high >= ob_low for c in candles[idx + 1 :])

    @staticmethod
    def _volume_score(candles: list[Candle], idx: int) -> float:
        if not candles or idx >= len(candles):
            return 0.5
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

    @staticmethod
    def _fvg_fill(p: SMCPattern, candles: list[Candle]) -> float:
        gap_low, gap_high = p.price_low, p.price_high
        if not gap_low or not gap_high or not candles:
            return 0.0
        gap_size = gap_high - gap_low
        if gap_size <= 0:
            return 100.0
        filled = 0.0
        for c in candles[-15:]:
            overlap = min(gap_high, c.high) - max(gap_low, c.low)
            if overlap > 0:
                filled = max(filled, overlap)
        return min(100.0, (filled / gap_size) * 100)

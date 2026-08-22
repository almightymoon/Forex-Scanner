"""Extract normalized market features from candles, indicators, and patterns.

Market structure is sourced exclusively from Market Structure Engine v1 over
confirmed swings. The extractor does not call legacy zigzag helpers or the
legacy structure analyzer for structure fields.
"""

from __future__ import annotations

from services.quant_engine.decision.session import current_session
from services.quant_engine.features.types import FVGFeatures, MarketFeatures, OrderBlockFeatures
from services.quant_engine.market_structure.detector import analyze_structure
from services.quant_engine.market_structure.integration import (
    build_trend_context_from_structure,
    structure_snapshot_to_features,
)
from services.quant_engine.market_structure.models import StructureInputError, StructureSnapshot
from services.quant_engine.swing_analysis import detect_session_liquidity
from services.quant_engine.swings.boundary import (
    FEATURE_SWING_VERSION,
    obtain_confirmed_swings,
)
from shared.types.models import Candle, IndicatorValues, SMCPattern, SignalDirection
from swing_engine.models import DetectedSwing


class FeatureExtractor:
    """Single pass feature extraction — all engines consume this output."""

    def __init__(self, swing_version: str = FEATURE_SWING_VERSION) -> None:
        self.swing_version = swing_version

    def extract(
        self,
        candles: list[Candle],
        indicators: IndicatorValues,
        patterns: list[SMCPattern],
        *,
        confirmed_swings: list[DetectedSwing] | None = None,
        structure_snapshot: StructureSnapshot | None = None,
        as_of_index: int | None = None,
    ) -> MarketFeatures:
        features = MarketFeatures()
        if not candles:
            return features

        swings = (
            list(confirmed_swings)
            if confirmed_swings is not None
            else obtain_confirmed_swings(candles, version=self.swing_version)
        )
        end = len(candles) - 1 if as_of_index is None else int(as_of_index)
        # Only swings confirmed within the analyzed prefix.
        swings = [
            s
            for s in swings
            if s.confirmation_index is not None and int(s.confirmation_index) <= end
        ]

        if structure_snapshot is not None and structure_snapshot.as_of_index == end:
            snapshot = structure_snapshot
        else:
            try:
                snapshot = analyze_structure(
                    candles,
                    swings,
                    as_of_index=end,
                )
            except StructureInputError:
                snapshot = analyze_structure(candles, [], as_of_index=end)

        mapped = structure_snapshot_to_features(snapshot, confirmed_swings=swings)
        ctx = build_trend_context_from_structure(
            snapshot,
            candles[: end + 1],
            indicators.ema_20,
            indicators.ema_50,
            confirmed_swings=swings,
        )

        features.structure_snapshot = mapped["structure_snapshot"]
        features.structure = mapped["structure"]
        features.trend_context = ctx
        features.trend_strength = ctx.strength
        features.trend_direction = mapped["trend_direction"]
        features.trend_maturity = ctx.maturity
        features.compression = ctx.compression
        features.expansion = ctx.expansion
        features.pullback = ctx.pullback

        features.swing_count = mapped["swing_count"]
        features.swing_strength_avg = mapped["swing_strength_avg"]
        features.bos_kind = mapped["bos_kind"]
        features.last_structure_event = mapped["last_structure_event"]
        features.structure_continuation = mapped["structure_continuation"]

        features.external_bias = mapped["external_bias"]
        features.pending_external_bias = mapped["pending_external_bias"]
        features.internal_bias = mapped["internal_bias"]
        features.pending_internal_bias = mapped["pending_internal_bias"]
        features.latest_external_high = mapped["latest_external_high"]
        features.latest_external_low = mapped["latest_external_low"]
        features.latest_internal_high = mapped["latest_internal_high"]
        features.latest_internal_low = mapped["latest_internal_low"]
        features.structural_sequence = list(mapped["structural_sequence"])
        features.structure_event_ids = list(mapped["structure_event_ids"])
        features.latest_structure_event_id = mapped["latest_structure_event_id"]
        features.latest_bos_choch = mapped["latest_bos_choch"]
        features.structure_metadata = dict(mapped["structure_metadata"])
        features.structure_metadata["swing_version"] = self.swing_version

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

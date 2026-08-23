"""Liquidity engine — Liquidity Engine v1 scoring adapter.

Detects / scores liquidity context for DecisionEngine. Directional BUY/SELL
from pattern points is retained for score aggregation only; trade decisions
remain outside this engine. Prefer ``analyze_liquidity`` for the full snapshot.
"""

from shared.config.scoring_loader import V2ScoringConfig, get_v2_scoring_config
from shared.types.models import Candle, SMCPattern, SignalDirection, TrendDirection

from services.quant_engine.features.types import MarketFeatures

from services.quant_engine.confidence.output import EngineOutput, clamp_score, confidence_from_score
from services.quant_engine.decision.pattern_scoring import filter_patterns
from services.quant_engine.liquidity.analyzer import analyze_liquidity
from services.quant_engine.liquidity.models import LIQUIDITY_ENGINE_VERSION, SweepKind, SweepQuality
from services.quant_engine.liquidity.pools import build_liquidity_map
from services.quant_engine.swing_analysis import detect_session_liquidity

_LIQUIDITY_TYPES = {"liquidity_sweep", "equal_highs", "equal_lows"}


class LiquidityEngine:
    version = LIQUIDITY_ENGINE_VERSION

    def __init__(self, config: V2ScoringConfig | None = None):
        self.config = config or get_v2_scoring_config()

    def analyze(
        self,
        candles: list[Candle],
        *,
        patterns: list[SMCPattern] | None = None,
        features: MarketFeatures | None = None,
        as_of_index: int | None = None,
    ):
        """Return LiquiditySnapshot (canonical v1 output)."""
        return analyze_liquidity(
            candles,
            snapshot=features.structure_snapshot if features else None,
            patterns=patterns or [],
            atr=features.atr if features else 0.0,
            external_bias=features.external_bias if features else None,
            as_of_index=as_of_index,
            symbol=candles[-1].symbol if candles else None,
            timeframe=candles[-1].timeframe if candles else None,
        )

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
        snapshot = None
        if features is not None and features.liquidity_snapshot is not None:
            # Prefer FeatureExtractor snapshot — avoid re-running analyze_liquidity.
            snapshot = features.liquidity_snapshot
            liquidity_map = snapshot.legacy_map or build_liquidity_map(
                patterns, features=features, candles=candles
            )
        elif candles:
            snapshot = self.analyze(candles, patterns=patterns, features=features)
            liquidity_map = snapshot.legacy_map or build_liquidity_map(
                patterns, features=features, candles=candles
            )
        else:
            liquidity_map = build_liquidity_map(
                patterns, features=features, candles=candles
            )

        score = 0
        reasons: list[str] = []
        warnings: list[str] = []
        buy_pts = sell_pts = 0

        sweep_by_dir = {
            (s.direction, s.level_price): s for s in liquidity_map.sweeps
        }

        for p in filtered:
            pts = rules.get(p.pattern_type, 3)
            if p.pattern_type == "liquidity_sweep":
                side = "buy_side" if p.direction == SignalDirection.BUY else "sell_side"
                pts += rules.get(side, 2)
                level = None
                if p.metadata:
                    raw = p.metadata.get("swept_level")
                    level = float(raw) if isinstance(raw, (int, float)) else None
                assessment = sweep_by_dir.get((p.direction, level))
                if assessment is None and liquidity_map.sweeps:
                    assessment = next(
                        (s for s in liquidity_map.sweeps if s.direction is p.direction),
                        None,
                    )
                if assessment is not None:
                    if assessment.quality is SweepQuality.CONTINUATION:
                        pts += 1
                        reasons.append(
                            f"Liquidity sweep continuation vs "
                            f"{(features.external_bias.value if features else 'bias')}"
                        )
                    elif assessment.quality is SweepQuality.STOP_HUNT:
                        pts = max(1, pts - 2)
                        warnings.append("Liquidity sweep conflicts with external bias")
                        reasons.extend(list(assessment.reasons[:1]))
                    else:
                        reasons.append(f"Liquidity sweep ({side.replace('_', ' ')})")
                else:
                    reasons.append(f"Liquidity sweep ({side.replace('_', ' ')})")
            elif p.pattern_type == "equal_highs":
                pts += rules.get("equal_highs", 3)
                reasons.append("Equal highs — sell-side liquidity pool")
                if features and features.external_bias is TrendDirection.BEARISH:
                    pts += 1
                    reasons.append("Equal highs align with bearish external bias")
            elif p.pattern_type == "equal_lows":
                pts += rules.get("equal_lows", 3)
                reasons.append("Equal lows — buy-side liquidity pool")
                if features and features.external_bias is TrendDirection.BULLISH:
                    pts += 1
                    reasons.append("Equal lows align with bullish external bias")
            score += pts
            if p.direction == SignalDirection.BUY:
                buy_pts += pts
            else:
                sell_pts += pts

        if snapshot is not None:
            reasons.append(
                f"Liquidity v{LIQUIDITY_ENGINE_VERSION}: "
                f"{len(snapshot.active_pools)} active pools, "
                f"{len(snapshot.recent_sweeps)} sweeps"
            )
            for event in snapshot.recent_sweeps[-2:]:
                reasons.append(
                    f"{event.kind.value} @ {event.level_price:.5f} "
                    f"grade={event.grade.value}"
                )

        session_tags = list(liquidity_map.session_tags) or (
            features.session_tags if features else detect_session_liquidity(candles or [])
        )
        pools = (
            features.liquidity_pools
            if features and features.liquidity_pools
            else liquidity_map.pool_labels
        )
        for tag in session_tags:
            if "sweep" in tag.lower():
                score += 2
            reasons.append(tag)

        score = clamp_score(score, weights.liquidity)
        # Score aggregation only — not a trade recommendation.
        direction = "BUY" if buy_pts > sell_pts else "SELL" if sell_pts > buy_pts else "NEUTRAL"
        return EngineOutput(
            name="Liquidity",
            score=score,
            max_score=weights.liquidity,
            confidence=confidence_from_score(score, weights.liquidity),
            direction=direction,
            reasons=reasons,
            warnings=warnings,
            metadata={
                "liquidity_pools": pools,
                "session_tags": session_tags,
                "liquidity_map": liquidity_map.to_dict(),
                "liquidity_snapshot": snapshot.to_dict() if snapshot else None,
                "liquidity_engine_version": LIQUIDITY_ENGINE_VERSION,
                "continuation_sweeps": sum(
                    1
                    for s in liquidity_map.sweeps
                    if s.quality is SweepQuality.CONTINUATION
                ),
                "stop_hunt_sweeps": sum(
                    1 for s in liquidity_map.sweeps if s.quality is SweepQuality.STOP_HUNT
                ),
                "breakouts": (
                    sum(1 for s in snapshot.sweeps if s.kind is SweepKind.BREAKOUT)
                    if snapshot
                    else 0
                ),
            },
        )

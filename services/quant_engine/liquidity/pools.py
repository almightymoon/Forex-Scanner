"""Build typed liquidity maps from SMC patterns + structure + session tags."""

from __future__ import annotations

from shared.types.models import SMCPattern, SignalDirection, TrendDirection

from services.quant_engine.features.types import MarketFeatures
from services.quant_engine.liquidity.models import (
    LiquidityKind,
    LiquidityLevel,
    LiquidityMap,
    LiquiditySide,
    LiquiditySweepAssessment,
    SweepQuality,
)
from services.quant_engine.market_structure.models import StructureRelation, StructureSnapshot
from services.quant_engine.swing_analysis import detect_session_liquidity
from shared.types.models import Candle


def assess_sweep_vs_bias(
    pattern: SMCPattern,
    external_bias: TrendDirection,
) -> LiquiditySweepAssessment:
    """Classify a liquidity sweep as continuation vs stop-hunt vs bias."""

    direction = pattern.direction
    level = pattern.metadata.get("swept_level") if pattern.metadata else None
    level_price = float(level) if isinstance(level, (int, float)) else None
    reasons: list[str] = []

    if external_bias is TrendDirection.RANGING:
        quality = SweepQuality.NEUTRAL
        agrees = False
        reasons.append("No external bias — sweep quality neutral")
    elif direction is SignalDirection.BUY and external_bias is TrendDirection.BULLISH:
        quality = SweepQuality.CONTINUATION
        agrees = True
        reasons.append("Buy-side sweep agrees with bullish external bias")
    elif direction is SignalDirection.SELL and external_bias is TrendDirection.BEARISH:
        quality = SweepQuality.CONTINUATION
        agrees = True
        reasons.append("Sell-side sweep agrees with bearish external bias")
    elif direction is SignalDirection.BUY and external_bias is TrendDirection.BEARISH:
        quality = SweepQuality.STOP_HUNT
        agrees = False
        reasons.append("Buy-side sweep against bearish bias — stop-hunt risk")
    elif direction is SignalDirection.SELL and external_bias is TrendDirection.BULLISH:
        quality = SweepQuality.STOP_HUNT
        agrees = False
        reasons.append("Sell-side sweep against bullish bias — stop-hunt risk")
    else:
        quality = SweepQuality.NEUTRAL
        agrees = False
        reasons.append("Sweep direction ambiguous vs bias")

    return LiquiditySweepAssessment(
        direction=direction,
        quality=quality,
        level_price=level_price,
        agrees_with_bias=agrees,
        reasons=tuple(reasons),
    )


def build_liquidity_map(
    patterns: list[SMCPattern],
    *,
    features: MarketFeatures | None = None,
    candles: list[Candle] | None = None,
    snapshot: StructureSnapshot | None = None,
) -> LiquidityMap:
    """Assemble typed levels and sweep assessments for scoring / confluence."""

    snap = snapshot or (features.structure_snapshot if features else None)
    external = features.external_bias if features else TrendDirection.RANGING
    session_tags = tuple(
        features.session_tags
        if features and features.session_tags
        else detect_session_liquidity(candles or [])
    )

    levels: list[LiquidityLevel] = []
    sweeps: list[LiquiditySweepAssessment] = []

    for pattern in patterns:
        if pattern.pattern_type == "equal_highs":
            price = pattern.price_high if pattern.price_high is not None else pattern.price_low
            if price is not None:
                levels.append(
                    LiquidityLevel(
                        kind=LiquidityKind.EQUAL_HIGHS,
                        side=LiquiditySide.SELL_SIDE,
                        price=float(price),
                        strength=float(pattern.strength or 0) / 100.0,
                        source="smc",
                    )
                )
        elif pattern.pattern_type == "equal_lows":
            price = pattern.price_low if pattern.price_low is not None else pattern.price_high
            if price is not None:
                levels.append(
                    LiquidityLevel(
                        kind=LiquidityKind.EQUAL_LOWS,
                        side=LiquiditySide.BUY_SIDE,
                        price=float(price),
                        strength=float(pattern.strength or 0) / 100.0,
                        source="smc",
                    )
                )
        elif pattern.pattern_type == "liquidity_sweep":
            sweeps.append(assess_sweep_vs_bias(pattern, external))
            level = pattern.metadata.get("swept_level") if pattern.metadata else None
            if isinstance(level, (int, float)):
                side = (
                    LiquiditySide.BUY_SIDE
                    if pattern.direction is SignalDirection.BUY
                    else LiquiditySide.SELL_SIDE
                )
                levels.append(
                    LiquidityLevel(
                        kind=LiquidityKind.SWEPT_LEVEL,
                        side=side,
                        price=float(level),
                        strength=float(pattern.strength or 0) / 100.0,
                        source="smc",
                        metadata={"sweep_direction": pattern.direction.value},
                    )
                )

    if snap is not None:
        for relation in snap.swing_relations[-8:]:
            if relation.relation is StructureRelation.EQUAL_HIGH:
                levels.append(
                    LiquidityLevel(
                        kind=LiquidityKind.EQUAL_HIGHS,
                        side=LiquiditySide.SELL_SIDE,
                        price=relation.price,
                        strength=0.55,
                        source="structure",
                        metadata={"swing_id": relation.swing_id},
                    )
                )
            elif relation.relation is StructureRelation.EQUAL_LOW:
                levels.append(
                    LiquidityLevel(
                        kind=LiquidityKind.EQUAL_LOWS,
                        side=LiquiditySide.BUY_SIDE,
                        price=relation.price,
                        strength=0.55,
                        source="structure",
                        metadata={"swing_id": relation.swing_id},
                    )
                )
        if snap.latest_external_high is not None:
            levels.append(
                LiquidityLevel(
                    kind=LiquidityKind.SWING_HIGH,
                    side=LiquiditySide.SELL_SIDE,
                    price=snap.latest_external_high,
                    strength=0.7,
                    source="structure",
                )
            )
        if snap.latest_external_low is not None:
            levels.append(
                LiquidityLevel(
                    kind=LiquidityKind.SWING_LOW,
                    side=LiquiditySide.BUY_SIDE,
                    price=snap.latest_external_low,
                    strength=0.7,
                    source="structure",
                )
            )

    for tag in session_tags:
        lower = tag.lower()
        if "asian high" in lower:
            levels.append(
                LiquidityLevel(
                    kind=LiquidityKind.SESSION_ASIA_HIGH,
                    side=LiquiditySide.SELL_SIDE,
                    price=0.0,
                    strength=0.4,
                    source="session",
                    metadata={"tag": tag},
                )
            )
        elif "asian low" in lower:
            levels.append(
                LiquidityLevel(
                    kind=LiquidityKind.SESSION_ASIA_LOW,
                    side=LiquiditySide.BUY_SIDE,
                    price=0.0,
                    strength=0.4,
                    source="session",
                    metadata={"tag": tag},
                )
            )

    return LiquidityMap(
        levels=tuple(levels),
        sweeps=tuple(sweeps),
        session_tags=session_tags,
    )

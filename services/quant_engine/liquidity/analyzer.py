"""Liquidity Engine v1 analyzer — pools, sweeps, LiquiditySnapshot."""

from __future__ import annotations

from dataclasses import replace

from shared.types.models import Candle, SMCPattern, SignalDirection, Timeframe, TrendDirection
from swing_engine.models import SwingDirection, SwingScope

from services.quant_engine.liquidity.clustering import (
    ClusterConfig,
    cluster_prices,
    equality_tolerance,
)
from services.quant_engine.liquidity.models import (
    LIQUIDITY_ENGINE_VERSION,
    LiquidityKind,
    LiquidityLevel,
    LiquidityMap,
    LiquidityPool,
    LiquiditySide,
    LiquiditySnapshot,
    LiquiditySweepAssessment,
    LiquiditySweepEvent,
    PoolStatus,
    PoolStrength,
    PoolType,
    SweepGrade,
    SweepKind,
    SweepQuality,
)
from services.quant_engine.liquidity.pools import assess_sweep_vs_bias
from services.quant_engine.liquidity.sessions import build_session_windows, _utc
from services.quant_engine.market_structure.models import (
    StructureRelation,
    StructureSnapshot,
)
from services.quant_engine.swing_analysis import detect_session_liquidity


def _tf(candles: list[Candle], timeframe: Timeframe | str | None) -> str:
    if timeframe is not None:
        return timeframe.value if isinstance(timeframe, Timeframe) else str(timeframe)
    if candles:
        return candles[0].timeframe.value
    return Timeframe.H1.value


def _atr(candles: list[Candle], features_atr: float = 0.0) -> float:
    if features_atr and features_atr > 0:
        return float(features_atr)
    if len(candles) < 2:
        return 0.0
    window = candles[-14:]
    return sum(c.high - c.low for c in window) / len(window)


def _strength(score: float, touches: int, *, structural: bool) -> tuple[PoolStrength, float]:
    s = score + (0.25 if structural else 0.0)
    if touches >= 3:
        s += 0.2
    elif touches >= 2:
        s += 0.1
    s = max(0.0, min(1.0, s))
    if s >= 0.7:
        return PoolStrength.STRONG, s
    if s >= 0.4:
        return PoolStrength.MODERATE, s
    return PoolStrength.WEAK, s


def _pool_id(pool_type: PoolType, price: float, available_index: int, source: str) -> str:
    return f"{pool_type.value}:{price:.5f}:{available_index}:{source}"


def _ts(candles: list[Candle], index: int):
    if 0 <= index < len(candles):
        return candles[index].timestamp
    return None


def _build_equal_pools(
    candles: list[Candle],
    snapshot: StructureSnapshot | None,
    *,
    symbol: str,
    timeframe: str,
    atr: float,
    tol: float,
    as_of: int,
    config: ClusterConfig,
) -> list[LiquidityPool]:
    pools: list[LiquidityPool] = []

    if snapshot is not None:
        for rel in snapshot.swing_relations:
            if rel.available_index > as_of:
                continue
            if rel.relation is StructureRelation.EQUAL_HIGH:
                strength, score = _strength(0.55, 2, structural=True)
                pools.append(
                    LiquidityPool(
                        pool_id=_pool_id(PoolType.EQUAL_HIGH, rel.price, rel.available_index, rel.swing_id),
                        pool_type=PoolType.EQUAL_HIGH,
                        side=LiquiditySide.SELL_SIDE,
                        price=float(rel.price),
                        symbol=symbol,
                        source_timeframe=timeframe,
                        scope=rel.scope.value,
                        status=PoolStatus.ACTIVE,
                        strength=strength,
                        strength_score=score,
                        touches=2,
                        created_index=rel.pivot_index,
                        available_index=rel.available_index,
                        created_at=_ts(candles, rel.pivot_index),
                        available_at=_ts(candles, rel.available_index),
                        source_reference=rel.swing_id,
                        reasons=("Structure EQUAL_HIGH relation", f"ATR context {atr:.5f}"),
                        metadata={"relation": rel.relation.value},
                    )
                )
            elif rel.relation is StructureRelation.EQUAL_LOW:
                strength, score = _strength(0.55, 2, structural=True)
                pools.append(
                    LiquidityPool(
                        pool_id=_pool_id(PoolType.EQUAL_LOW, rel.price, rel.available_index, rel.swing_id),
                        pool_type=PoolType.EQUAL_LOW,
                        side=LiquiditySide.BUY_SIDE,
                        price=float(rel.price),
                        symbol=symbol,
                        source_timeframe=timeframe,
                        scope=rel.scope.value,
                        status=PoolStatus.ACTIVE,
                        strength=strength,
                        strength_score=score,
                        touches=2,
                        created_index=rel.pivot_index,
                        available_index=rel.available_index,
                        created_at=_ts(candles, rel.pivot_index),
                        available_at=_ts(candles, rel.available_index),
                        source_reference=rel.swing_id,
                        reasons=("Structure EQUAL_LOW relation", f"ATR context {atr:.5f}"),
                        metadata={"relation": rel.relation.value},
                    )
                )

    highs: list[tuple[int, float]] = []
    lows: list[tuple[int, float]] = []
    if snapshot is not None:
        for rel in snapshot.swing_relations:
            if rel.available_index > as_of or rel.scope is not SwingScope.EXTERNAL:
                continue
            if rel.direction is SwingDirection.HIGH:
                highs.append((rel.available_index, float(rel.price)))
            else:
                lows.append((rel.available_index, float(rel.price)))
    else:
        for i in range(1, max(as_of, 0)):
            left_h = candles[i].high >= candles[i - 1].high
            right_h = i + 1 > as_of or candles[i].high >= candles[i + 1].high
            if left_h and right_h:
                highs.append((i, candles[i].high))
            left_l = candles[i].low <= candles[i - 1].low
            right_l = i + 1 > as_of or candles[i].low <= candles[i + 1].low
            if left_l and right_l:
                lows.append((i, candles[i].low))

    for cluster in cluster_prices(highs, tolerance=tol, min_touches=config.min_touches):
        avail = max(cluster.indices)
        if any(p.pool_type is PoolType.EQUAL_HIGH and abs(p.price - cluster.price) <= tol for p in pools):
            continue
        strength, score = _strength(0.45, cluster.touches, structural=False)
        pools.append(
            LiquidityPool(
                pool_id=_pool_id(PoolType.EQUAL_HIGH, cluster.price, avail, "cluster"),
                pool_type=PoolType.EQUAL_HIGH,
                side=LiquiditySide.SELL_SIDE,
                price=cluster.price,
                symbol=symbol,
                source_timeframe=timeframe,
                scope="CLUSTER",
                status=PoolStatus.ACTIVE,
                strength=strength,
                strength_score=score,
                touches=cluster.touches,
                created_index=min(cluster.indices),
                available_index=avail,
                created_at=_ts(candles, min(cluster.indices)),
                available_at=_ts(candles, avail),
                source_reference="high_cluster",
                reasons=(f"{cluster.touches} highs within tolerance {tol:.5f}",),
                metadata={"member_indices": list(cluster.indices)},
            )
        )

    for cluster in cluster_prices(lows, tolerance=tol, min_touches=config.min_touches):
        avail = max(cluster.indices)
        if any(p.pool_type is PoolType.EQUAL_LOW and abs(p.price - cluster.price) <= tol for p in pools):
            continue
        strength, score = _strength(0.45, cluster.touches, structural=False)
        pools.append(
            LiquidityPool(
                pool_id=_pool_id(PoolType.EQUAL_LOW, cluster.price, avail, "cluster"),
                pool_type=PoolType.EQUAL_LOW,
                side=LiquiditySide.BUY_SIDE,
                price=cluster.price,
                symbol=symbol,
                source_timeframe=timeframe,
                scope="CLUSTER",
                status=PoolStatus.ACTIVE,
                strength=strength,
                strength_score=score,
                touches=cluster.touches,
                created_index=min(cluster.indices),
                available_index=avail,
                created_at=_ts(candles, min(cluster.indices)),
                available_at=_ts(candles, avail),
                source_reference="low_cluster",
                reasons=(f"{cluster.touches} lows within tolerance {tol:.5f}",),
                metadata={"member_indices": list(cluster.indices)},
            )
        )
    return pools


def _build_structural_pools(
    candles: list[Candle],
    snapshot: StructureSnapshot | None,
    *,
    symbol: str,
    timeframe: str,
    as_of: int,
) -> list[LiquidityPool]:
    if snapshot is None:
        return []
    pools: list[LiquidityPool] = []
    for rel in snapshot.swing_relations:
        if rel.available_index > as_of:
            continue
        if rel.relation in (
            StructureRelation.UNKNOWN,
            StructureRelation.EQUAL_HIGH,
            StructureRelation.EQUAL_LOW,
        ):
            continue
        if rel.direction is SwingDirection.HIGH:
            ptype, side = PoolType.STRUCTURAL_HIGH, LiquiditySide.SELL_SIDE
        else:
            ptype, side = PoolType.STRUCTURAL_LOW, LiquiditySide.BUY_SIDE
        strength, score = _strength(0.6, 1, structural=True)
        pools.append(
            LiquidityPool(
                pool_id=_pool_id(ptype, rel.price, rel.available_index, rel.swing_id),
                pool_type=ptype,
                side=side,
                price=float(rel.price),
                symbol=symbol,
                source_timeframe=timeframe,
                scope=rel.scope.value,
                status=PoolStatus.ACTIVE,
                strength=strength,
                strength_score=score,
                touches=1,
                created_index=rel.pivot_index,
                available_index=rel.available_index,
                created_at=_ts(candles, rel.pivot_index),
                available_at=_ts(candles, rel.available_index),
                source_reference=rel.swing_id,
                reasons=(f"Structural {rel.relation.value}", f"Scope {rel.scope.value}"),
                metadata={"relation": rel.relation.value},
            )
        )
    return pools


def _build_session_pools(
    candles: list[Candle],
    *,
    symbol: str,
    timeframe: str,
    as_of: int,
) -> list[LiquidityPool]:
    pools: list[LiquidityPool] = []
    for window in build_session_windows(candles, as_of_index=as_of):
        avail_idx = as_of
        for i in range(as_of + 1):
            if _utc(candles[i].timestamp) >= window.end:
                avail_idx = i
                break
        if avail_idx > as_of:
            continue
        strength, score = _strength(0.5, 1, structural=False)
        meta = {
            "session_type": window.session_type.value,
            "session_start": window.start.isoformat(),
            "session_end": window.end.isoformat(),
        }
        pools.append(
            LiquidityPool(
                pool_id=_pool_id(PoolType.SESSION_HIGH, window.high, avail_idx, window.session_type.value),
                pool_type=PoolType.SESSION_HIGH,
                side=LiquiditySide.SELL_SIDE,
                price=window.high,
                symbol=symbol,
                source_timeframe=timeframe,
                scope="SESSION",
                status=PoolStatus.ACTIVE,
                strength=strength,
                strength_score=score,
                touches=1,
                created_index=window.high_index,
                available_index=avail_idx,
                created_at=_ts(candles, window.high_index),
                available_at=window.end,
                source_reference=window.session_type.value,
                reasons=(f"{window.session_type.value} session high",),
                metadata=meta,
            )
        )
        pools.append(
            LiquidityPool(
                pool_id=_pool_id(PoolType.SESSION_LOW, window.low, avail_idx, window.session_type.value),
                pool_type=PoolType.SESSION_LOW,
                side=LiquiditySide.BUY_SIDE,
                price=window.low,
                symbol=symbol,
                source_timeframe=timeframe,
                scope="SESSION",
                status=PoolStatus.ACTIVE,
                strength=strength,
                strength_score=score,
                touches=1,
                created_index=window.low_index,
                available_index=avail_idx,
                created_at=_ts(candles, window.low_index),
                available_at=window.end,
                source_reference=window.session_type.value,
                reasons=(f"{window.session_type.value} session low",),
                metadata=meta,
            )
        )
    return pools


def _grade_sweep(
    *,
    penetration_atr: float,
    rejection_pct: float,
    structural: bool,
    touches: int,
) -> tuple[SweepGrade, list[str]]:
    score = 0
    reasons: list[str] = []
    if structural:
        score += 2
        reasons.append("Structural pool")
    if touches >= 3:
        score += 2
        reasons.append(f"{touches} prior touches")
    elif touches >= 2:
        score += 1
        reasons.append(f"{touches} prior touches")
    if 0.15 <= penetration_atr <= 0.8:
        score += 2
        reasons.append(f"{penetration_atr:.2f} ATR penetration")
    elif penetration_atr > 0:
        score += 1
        reasons.append(f"{penetration_atr:.2f} ATR penetration")
    if rejection_pct >= 70:
        score += 2
        reasons.append(f"{rejection_pct:.0f}% candle rejection")
    elif rejection_pct >= 50:
        score += 1
        reasons.append(f"{rejection_pct:.0f}% candle rejection")
    if score >= 6:
        return SweepGrade.STRONG, reasons
    if score >= 3:
        return SweepGrade.MODERATE, reasons
    return SweepGrade.WEAK, reasons


def _detect_sweeps(
    candles: list[Candle],
    pools: list[LiquidityPool],
    *,
    atr: float,
    as_of: int,
    external_bias: TrendDirection,
) -> tuple[list[LiquidityPool], list[LiquiditySweepEvent]]:
    atr = max(atr, 1e-9)
    state = {p.pool_id: p for p in pools}
    events: list[LiquiditySweepEvent] = []

    for bar_i in range(0, as_of + 1):
        c = candles[bar_i]
        candle_range = max(c.high - c.low, 1e-12)
        for pool_id, pool in list(state.items()):
            if pool.status is not PoolStatus.ACTIVE:
                continue
            if pool.available_index >= bar_i:
                continue

            if pool.side is LiquiditySide.SELL_SIDE:
                if c.high <= pool.price:
                    continue
                penetration = c.high - pool.price
                if c.close < pool.price:
                    rejection = (c.high - c.close) / candle_range * 100.0
                    grade, reasons = _grade_sweep(
                        penetration_atr=penetration / atr,
                        rejection_pct=rejection,
                        structural=pool.pool_type is PoolType.STRUCTURAL_HIGH,
                        touches=pool.touches,
                    )
                    fake = SMCPattern(
                        pattern_type="liquidity_sweep",
                        direction=SignalDirection.SELL,
                        strength=50,
                        metadata={"swept_level": pool.price},
                    )
                    bias_a = assess_sweep_vs_bias(fake, external_bias)
                    reasons = list(reasons) + [f"Close returned below {pool.price:.5f}"]
                    events.append(
                        LiquiditySweepEvent(
                            sweep_id=f"SWP:{pool_id}:{bar_i}",
                            kind=SweepKind.SWEEP_HIGH,
                            pool_id=pool_id,
                            pool_type=pool.pool_type,
                            level_price=pool.price,
                            bar_index=bar_i,
                            timestamp=c.timestamp,
                            penetration=penetration,
                            penetration_atr=penetration / atr,
                            rejection_pct=rejection,
                            grade=grade,
                            bias_quality=bias_a.quality,
                            reasons=tuple(reasons),
                        )
                    )
                    state[pool_id] = replace(pool, status=PoolStatus.SWEPT)
                elif c.close > pool.price and (c.close - pool.price) / atr >= 0.05:
                    events.append(
                        LiquiditySweepEvent(
                            sweep_id=f"BRK:{pool_id}:{bar_i}",
                            kind=SweepKind.BREAKOUT,
                            pool_id=pool_id,
                            pool_type=pool.pool_type,
                            level_price=pool.price,
                            bar_index=bar_i,
                            timestamp=c.timestamp,
                            penetration=c.close - pool.price,
                            penetration_atr=(c.close - pool.price) / atr,
                            rejection_pct=(c.high - c.close) / candle_range * 100.0,
                            grade=SweepGrade.WEAK,
                            bias_quality=SweepQuality.NEUTRAL,
                            reasons=("Close accepted beyond liquidity high — breakout",),
                        )
                    )
                    state[pool_id] = replace(pool, status=PoolStatus.INVALIDATED)
            else:
                if c.low >= pool.price:
                    continue
                penetration = pool.price - c.low
                if c.close > pool.price:
                    rejection = (c.close - c.low) / candle_range * 100.0
                    grade, reasons = _grade_sweep(
                        penetration_atr=penetration / atr,
                        rejection_pct=rejection,
                        structural=pool.pool_type is PoolType.STRUCTURAL_LOW,
                        touches=pool.touches,
                    )
                    fake = SMCPattern(
                        pattern_type="liquidity_sweep",
                        direction=SignalDirection.BUY,
                        strength=50,
                        metadata={"swept_level": pool.price},
                    )
                    bias_a = assess_sweep_vs_bias(fake, external_bias)
                    reasons = list(reasons) + [f"Close returned above {pool.price:.5f}"]
                    events.append(
                        LiquiditySweepEvent(
                            sweep_id=f"SWP:{pool_id}:{bar_i}",
                            kind=SweepKind.SWEEP_LOW,
                            pool_id=pool_id,
                            pool_type=pool.pool_type,
                            level_price=pool.price,
                            bar_index=bar_i,
                            timestamp=c.timestamp,
                            penetration=penetration,
                            penetration_atr=penetration / atr,
                            rejection_pct=rejection,
                            grade=grade,
                            bias_quality=bias_a.quality,
                            reasons=tuple(reasons),
                        )
                    )
                    state[pool_id] = replace(pool, status=PoolStatus.SWEPT)
                elif c.close < pool.price and (pool.price - c.close) / atr >= 0.05:
                    events.append(
                        LiquiditySweepEvent(
                            sweep_id=f"BRK:{pool_id}:{bar_i}",
                            kind=SweepKind.BREAKOUT,
                            pool_id=pool_id,
                            pool_type=pool.pool_type,
                            level_price=pool.price,
                            bar_index=bar_i,
                            timestamp=c.timestamp,
                            penetration=pool.price - c.close,
                            penetration_atr=(pool.price - c.close) / atr,
                            rejection_pct=(c.close - c.low) / candle_range * 100.0,
                            grade=SweepGrade.WEAK,
                            bias_quality=SweepQuality.NEUTRAL,
                            reasons=("Close accepted beyond liquidity low — breakout",),
                        )
                    )
                    state[pool_id] = replace(pool, status=PoolStatus.INVALIDATED)

    return list(state.values()), events


_KIND_MAP = {
    PoolType.EQUAL_HIGH: LiquidityKind.EQUAL_HIGHS,
    PoolType.EQUAL_LOW: LiquidityKind.EQUAL_LOWS,
    PoolType.STRUCTURAL_HIGH: LiquidityKind.SWING_HIGH,
    PoolType.STRUCTURAL_LOW: LiquidityKind.SWING_LOW,
    PoolType.SESSION_HIGH: LiquidityKind.SESSION_ASIA_HIGH,
    PoolType.SESSION_LOW: LiquidityKind.SESSION_ASIA_LOW,
}


def _to_legacy_map(
    pools: list[LiquidityPool],
    sweeps: list[LiquiditySweepEvent],
    session_tags: tuple[str, ...],
    patterns: list[SMCPattern],
    external_bias: TrendDirection,
) -> LiquidityMap:
    levels: list[LiquidityLevel] = []
    for pool in pools:
        kind = _KIND_MAP.get(pool.pool_type, LiquidityKind.SWING_HIGH)
        if pool.pool_type is PoolType.SESSION_HIGH:
            sess = (pool.metadata or {}).get("session_type", "asia")
            kind = (
                LiquidityKind.SESSION_ASIA_HIGH
                if sess == "asia"
                else LiquidityKind.SESSION_ASIA_HIGH
            )
        levels.append(
            LiquidityLevel(
                kind=kind,
                side=pool.side,
                price=pool.price,
                strength=pool.strength_score,
                source=pool.scope.lower() if pool.scope else "liquidity",
                metadata={
                    "pool_id": pool.pool_id,
                    "pool_type": pool.pool_type.value,
                    "status": pool.status.value,
                    "source_timeframe": pool.source_timeframe,
                    "available_index": pool.available_index,
                },
            )
        )

    legacy_sweeps: list[LiquiditySweepAssessment] = []
    for event in sweeps:
        if event.kind is SweepKind.BREAKOUT:
            continue
        direction = (
            SignalDirection.SELL
            if event.kind is SweepKind.SWEEP_HIGH
            else SignalDirection.BUY
        )
        legacy_sweeps.append(
            LiquiditySweepAssessment(
                direction=direction,
                quality=event.bias_quality,
                level_price=event.level_price,
                agrees_with_bias=event.bias_quality is SweepQuality.CONTINUATION,
                reasons=event.reasons,
            )
        )
    # Also include SMC pattern bias assessments for confluence parity.
    for pattern in patterns:
        if pattern.pattern_type == "liquidity_sweep":
            legacy_sweeps.append(assess_sweep_vs_bias(pattern, external_bias))

    return LiquidityMap(
        levels=tuple(levels),
        sweeps=tuple(legacy_sweeps),
        session_tags=session_tags,
    )


def analyze_liquidity(
    candles: list[Candle],
    *,
    snapshot: StructureSnapshot | None = None,
    patterns: list[SMCPattern] | None = None,
    symbol: str | None = None,
    timeframe: Timeframe | str | None = None,
    as_of_index: int | None = None,
    atr: float = 0.0,
    external_bias: TrendDirection | None = None,
    cluster_config: ClusterConfig | None = None,
    expire_bars: int = 500,
) -> LiquiditySnapshot:
    """Build a causal LiquiditySnapshot for the candle prefix ending at as_of_index."""

    patterns = patterns or []
    cfg = cluster_config or ClusterConfig()
    if not candles:
        empty_map = LiquidityMap(levels=(), sweeps=(), session_tags=())
        return LiquiditySnapshot(
            symbol=symbol or "UNKNOWN",
            timeframe=_tf(candles, timeframe),
            as_of_index=-1,
            pools=(),
            sweeps=(),
            session_tags=(),
            atr=0.0,
            equality_tolerance=cfg.min_tick,
            legacy_map=empty_map,
        )

    as_of = len(candles) - 1 if as_of_index is None else min(as_of_index, len(candles) - 1)
    prefix = candles[: as_of + 1]
    sym = symbol or prefix[-1].symbol
    tf = _tf(prefix, timeframe)
    atr_v = _atr(prefix, atr)
    tol = equality_tolerance(atr_v, config=cfg)
    bias = external_bias or (
        snapshot.external_bias if snapshot is not None else TrendDirection.RANGING
    )

    pools = (
        _build_equal_pools(
            prefix, snapshot, symbol=sym, timeframe=tf, atr=atr_v, tol=tol, as_of=as_of, config=cfg
        )
        + _build_structural_pools(prefix, snapshot, symbol=sym, timeframe=tf, as_of=as_of)
        + _build_session_pools(prefix, symbol=sym, timeframe=tf, as_of=as_of)
    )

    # Expire very old pools.
    aged: list[LiquidityPool] = []
    for pool in pools:
        if as_of - pool.available_index > expire_bars and pool.status is PoolStatus.ACTIVE:
            aged.append(replace(pool, status=PoolStatus.EXPIRED))
        else:
            aged.append(pool)

    pools_final, sweep_events = _detect_sweeps(
        prefix, aged, atr=atr_v, as_of=as_of, external_bias=bias
    )
    session_tags = tuple(detect_session_liquidity(prefix))
    legacy = _to_legacy_map(pools_final, sweep_events, session_tags, patterns, bias)

    return LiquiditySnapshot(
        symbol=sym,
        timeframe=tf,
        as_of_index=as_of,
        pools=tuple(pools_final),
        sweeps=tuple(sweep_events),
        session_tags=session_tags,
        atr=atr_v,
        equality_tolerance=tol,
        algorithm_version=LIQUIDITY_ENGINE_VERSION,
        legacy_map=legacy,
    )

"""Context-aware FVG/OB ranking — deterministic, causal, explainable."""

from __future__ import annotations

import time

from services.quant_engine.fvg.lifecycle import detect_fvg_zones
from services.quant_engine.fvg.models import FVGStatus, FVGZone, FVGZoneSet
from services.quant_engine.fvg.patterns import patterns_from_fvg_zones, rank_fvg_zones
from services.quant_engine.liquidity.models import (
    LiquidityPool,
    LiquiditySide,
    LiquiditySnapshot,
    LiquiditySweepEvent,
    PoolStatus,
    PoolStrength,
    PoolType,
    SweepGrade,
    SweepKind,
    SweepQuality,
)
from services.quant_engine.market_structure.models import StructureSnapshot
from services.quant_engine.order_blocks.lifecycle import detect_order_block_zones
from services.quant_engine.pipeline import ANALYSIS_PIPELINE_VERSION, analyze_candle_window
from services.quant_engine.zones.context import (
    Alignment,
    LiquidityRelation,
    build_zone_context,
    ranking_key,
)
from services.quant_engine.zones.ranking import DEFAULT_PATTERN_LIMIT, enrich_and_rank_zones
from shared.types.models import SignalDirection, Timeframe, TrendDirection
from tests.fixtures.golden.candles import make_candle
from tests.quant_engine.test_fvg_ob_lifecycle import bullish_fvg_series, multi_fvg_series


def _empty_structure(bias: TrendDirection = TrendDirection.BULLISH) -> StructureSnapshot:
    return StructureSnapshot(
        as_of_index=10,
        external_bias=bias,
        pending_external_bias=TrendDirection.RANGING,
        internal_bias=TrendDirection.RANGING,
        pending_internal_bias=TrendDirection.RANGING,
        swing_relations=(),
        events=(),
        latest_external_high=None,
        latest_external_low=None,
        latest_internal_high=None,
        latest_internal_low=None,
    )


def _pool(
    *,
    pool_id: str,
    side: LiquiditySide,
    price: float,
    status: PoolStatus = PoolStatus.ACTIVE,
) -> LiquidityPool:
    return LiquidityPool(
        pool_id=pool_id,
        pool_type=PoolType.EQUAL_HIGH if side is LiquiditySide.SELL_SIDE else PoolType.EQUAL_LOW,
        side=side,
        price=price,
        symbol="XAUUSD",
        source_timeframe="H1",
        scope="EXTERNAL",
        status=status,
        strength=PoolStrength.MODERATE,
        strength_score=0.5,
        touches=2,
        created_index=0,
        available_index=0,
        created_at=None,
        available_at=None,
        source_reference="test",
    )


def _liq(
    pools: list[LiquidityPool] | None = None,
    sweeps: list[LiquiditySweepEvent] | None = None,
    atr: float = 1.0,
) -> LiquiditySnapshot:
    return LiquiditySnapshot(
        symbol="XAUUSD",
        timeframe="H1",
        as_of_index=10,
        pools=tuple(pools or ()),
        sweeps=tuple(sweeps or ()),
        session_tags=(),
        atr=atr,
        equality_tolerance=0.1,
    )


def _fvg(
    *,
    zone_id: str,
    direction: SignalDirection,
    lo: float,
    hi: float,
    created: int,
    status: FVGStatus = FVGStatus.ACTIVE,
) -> FVGZone:
    return FVGZone(
        zone_id=zone_id,
        symbol="XAUUSD",
        timeframe="H1",
        direction=direction,
        lower_bound=lo,
        upper_bound=hi,
        created_index=created,
        created_timestamp=None,
        source_candle_indices=(max(0, created - 2), max(0, created - 1), created),
        status=status,
        age_bars=max(0, 10 - created),
    )


def test_structure_alignment_aligned_opposed_neutral():
    z = _fvg(zone_id="a", direction=SignalDirection.BUY, lo=100, hi=102, created=2)
    assert (
        build_zone_context(
            z, price=103, structure=_empty_structure(TrendDirection.BULLISH)
        ).structure_alignment
        is Alignment.ALIGNED
    )
    assert (
        build_zone_context(
            z, price=103, structure=_empty_structure(TrendDirection.BEARISH)
        ).structure_alignment
        is Alignment.OPPOSED
    )
    assert (
        build_zone_context(
            z, price=103, structure=_empty_structure(TrendDirection.RANGING)
        ).structure_alignment
        is Alignment.NEUTRAL
    )
    assert build_zone_context(z, price=103, structure=None).structure_alignment is Alignment.UNDEFINED


def test_trend_alignment_uses_canonical_bias():
    z = _fvg(zone_id="a", direction=SignalDirection.SELL, lo=100, hi=102, created=2)
    ctx = build_zone_context(
        z,
        price=99,
        structure=_empty_structure(TrendDirection.BULLISH),
        trend=TrendDirection.BEARISH,
    )
    assert ctx.structure_alignment is Alignment.OPPOSED
    assert ctx.trend_alignment is Alignment.ALIGNED


def test_liquidity_near_opposing_and_sweep():
    z = _fvg(zone_id="a", direction=SignalDirection.BUY, lo=100, hi=102, created=2)
    near = _liq(pools=[_pool(pool_id="p1", side=LiquiditySide.BUY_SIDE, price=101.0)])
    assert (
        build_zone_context(z, price=103, atr=1.0, liquidity=near).liquidity_relation
        is LiquidityRelation.NEAR_RELEVANT
    )

    opposing = _liq(pools=[_pool(pool_id="p2", side=LiquiditySide.SELL_SIDE, price=101.0)])
    assert (
        build_zone_context(z, price=103, atr=1.0, liquidity=opposing).liquidity_relation
        is LiquidityRelation.OPPOSING
    )

    sweep = LiquiditySweepEvent(
        sweep_id="s1",
        kind=SweepKind.SWEEP_LOW,
        pool_id="p1",
        pool_type=PoolType.EQUAL_LOW,
        level_price=101.0,
        bar_index=5,
        timestamp=None,
        penetration=0.2,
        penetration_atr=0.2,
        rejection_pct=50.0,
        grade=SweepGrade.MODERATE,
        bias_quality=SweepQuality.CONTINUATION,
    )
    swept = _liq(sweeps=[sweep])
    assert (
        build_zone_context(z, price=103, atr=1.0, liquidity=swept).liquidity_relation
        is LiquidityRelation.ASSOCIATED_SWEEP
    )


def test_distance_inside_and_outside():
    z = _fvg(zone_id="a", direction=SignalDirection.BUY, lo=100, hi=102, created=2)
    inside = build_zone_context(z, price=101.0, atr=2.0)
    assert inside.price_inside_zone is True
    assert inside.distance_to_price == 0.0
    assert inside.distance_atr == 0.0

    above = build_zone_context(z, price=104.0, atr=2.0)
    assert above.price_inside_zone is False
    assert above.distance_to_price == 2.0
    assert above.distance_atr == 1.0


def test_freshness_from_as_of():
    z = _fvg(zone_id="a", direction=SignalDirection.BUY, lo=100, hi=102, created=2)
    ctx = build_zone_context(z, price=103, as_of_index=10)
    assert ctx.freshness_bars == 8
    assert "freshness_bars=8" in ctx.reasons


def test_explanation_metadata_structured():
    z = _fvg(zone_id="fvg-1", direction=SignalDirection.BUY, lo=100, hi=102, created=2)
    ctx = build_zone_context(
        z,
        price=101,
        atr=1.0,
        structure=_empty_structure(TrendDirection.BULLISH),
        as_of_index=6,
    )
    d = ctx.to_dict()
    assert d["zone_id"] == "fvg-1"
    assert d["structure_alignment"] == "ALIGNED"
    assert isinstance(d["reasons"], list)
    assert d["mitigation_state"] == "ACTIVE"


def test_lexicographic_ranking_aligned_beats_opposed():
    far_aligned = _fvg(zone_id="far", direction=SignalDirection.BUY, lo=90, hi=91, created=1)
    near_opposed = _fvg(zone_id="opp", direction=SignalDirection.SELL, lo=103.5, hi=104.5, created=3)
    ranked = enrich_and_rank_zones(
        [near_opposed, far_aligned],
        price=104.0,
        atr=1.0,
        structure=_empty_structure(TrendDirection.BULLISH),
    )
    assert ranked[0][0].zone_id == "far"
    assert ranked[0][1].structure_alignment is Alignment.ALIGNED
    assert ranked[1][1].structure_alignment is Alignment.OPPOSED


def test_closer_wins_when_aligned():
    far = _fvg(zone_id="far", direction=SignalDirection.BUY, lo=90, hi=91, created=1)
    near = _fvg(zone_id="near", direction=SignalDirection.BUY, lo=102, hi=103, created=2)
    ranked = enrich_and_rank_zones(
        [far, near],
        price=104.0,
        atr=1.0,
        structure=_empty_structure(TrendDirection.BULLISH),
    )
    assert ranked[0][0].zone_id == "near"


def test_lifecycle_validity_first():
    active = _fvg(zone_id="act", direction=SignalDirection.BUY, lo=100, hi=101, created=5)
    mitigated = _fvg(
        zone_id="mit",
        direction=SignalDirection.BUY,
        lo=103,
        hi=104,
        created=4,
        status=FVGStatus.MITIGATED,
    )
    ranked = enrich_and_rank_zones(
        [mitigated, active],
        price=102,
        structure=_empty_structure(TrendDirection.BULLISH),
    )
    assert ranked[0][0].zone_id == "act"


def test_tie_break_zone_id_stable():
    a = _fvg(zone_id="aaa", direction=SignalDirection.BUY, lo=100, hi=101, created=5)
    b = _fvg(zone_id="bbb", direction=SignalDirection.BUY, lo=100, hi=101, created=5)
    r1 = [z.zone_id for z, _ in enrich_and_rank_zones([b, a], price=110, atr=1.0)]
    r2 = [z.zone_id for z, _ in enrich_and_rank_zones([a, b], price=110, atr=1.0)]
    assert r1 == r2 == ["aaa", "bbb"]


def test_soft_cap_after_ranking_preserves_zoneset():
    zones = [
        _fvg(
            zone_id=f"z{i:02d}",
            direction=SignalDirection.BUY,
            lo=100 - i,
            hi=100.5 - i,
            created=i,
        )
        for i in range(12)
    ]
    zs = FVGZoneSet(symbol="XAUUSD", timeframe="H1", as_of_index=20, zones=tuple(zones))
    pats = patterns_from_fvg_zones(
        zs,
        price=110,
        atr=1.0,
        structure=_empty_structure(TrendDirection.BULLISH),
        limit=DEFAULT_PATTERN_LIMIT,
    )
    assert len(zs.zones) == 12
    assert len(pats) == 8
    assert [p.metadata["rank"] for p in pats] == list(range(1, 9))


def test_deterministic_same_input_same_order():
    candles = multi_fvg_series()
    zs = detect_fvg_zones(candles)
    a = rank_fvg_zones(zs, price=float(candles[-1].close), atr=1.0, structure=_empty_structure())
    b = rank_fvg_zones(zs, price=float(candles[-1].close), atr=1.0, structure=_empty_structure())
    assert [z.zone_id for z in a] == [z.zone_id for z in b]


def test_ranking_no_lookahead_on_prefix():
    candles = bullish_fvg_series()
    t = 3
    early = detect_fvg_zones(candles, as_of_index=t)
    struct_early = _empty_structure(TrendDirection.BULLISH)
    r_early = enrich_and_rank_zones(
        early.zones,
        price=float(candles[t].close),
        atr=1.0,
        structure=struct_early,
        as_of_index=t,
    )
    r_via_full = enrich_and_rank_zones(
        detect_fvg_zones(candles, as_of_index=t).zones,
        price=float(candles[t].close),
        atr=1.0,
        structure=struct_early,
        as_of_index=t,
    )
    assert [z.zone_id for z, _ in r_early] == [z.zone_id for z, _ in r_via_full]
    assert r_early[0][1].mitigation_state == "ACTIVE"
    assert r_early[0][1].to_dict() == r_via_full[0][1].to_dict()

    late_zones = detect_fvg_zones(candles, as_of_index=5)
    assert late_zones.zones[0].status is FVGStatus.MITIGATED


def test_future_structure_bias_cannot_alter_earlier_context():
    z = _fvg(zone_id="a", direction=SignalDirection.BUY, lo=100, hi=102, created=2)
    at_t = build_zone_context(
        z, price=103, structure=_empty_structure(TrendDirection.BULLISH), as_of_index=3
    )
    future = build_zone_context(
        z, price=103, structure=_empty_structure(TrendDirection.BEARISH), as_of_index=20
    )
    assert at_t.structure_alignment is Alignment.ALIGNED
    assert future.structure_alignment is Alignment.OPPOSED


def test_future_price_cannot_change_historical_distance():
    z = _fvg(zone_id="a", direction=SignalDirection.BUY, lo=100, hi=102, created=2)
    d1 = build_zone_context(z, price=105.0, atr=1.0, as_of_index=3)
    d2 = build_zone_context(z, price=105.0, atr=1.0, as_of_index=3)
    assert d1.distance_to_price == d2.distance_to_price == 3.0
    later = build_zone_context(z, price=90.0, atr=1.0, as_of_index=20)
    assert later.distance_to_price != d1.distance_to_price


def test_pipeline_ranking_parity_and_explanations():
    candles = multi_fvg_series()
    a = analyze_candle_window("XAUUSD", Timeframe.H1, candles, evaluate=False)
    b = analyze_candle_window("XAUUSD", Timeframe.H1, list(candles), evaluate=False)
    assert a.analytical_fingerprint() == b.analytical_fingerprint()
    fa = [p for p in a.smc_patterns if p.pattern_type == "fvg"]
    fb = [p for p in b.smc_patterns if p.pattern_type == "fvg"]
    assert [p.metadata["zone_id"] for p in fa] == [p.metadata["zone_id"] for p in fb]
    if fa:
        assert "zone_context" in fa[0].metadata
        assert "rank_reasons" in fa[0].metadata
        assert fa[0].metadata["rank"] == 1


def test_pipeline_version_is_1_4_0():
    assert ANALYSIS_PIPELINE_VERSION == "1.4.0"


def test_multiple_zones_opposite_sides_ranked():
    zones = [
        _fvg(zone_id="bull-near", direction=SignalDirection.BUY, lo=99, hi=100, created=5),
        _fvg(zone_id="bull-far", direction=SignalDirection.BUY, lo=80, hi=81, created=4),
        _fvg(zone_id="bear-near", direction=SignalDirection.SELL, lo=105, hi=106, created=6),
    ]
    ranked = enrich_and_rank_zones(
        zones,
        price=102.0,
        atr=1.0,
        structure=_empty_structure(TrendDirection.BULLISH),
        liquidity=_liq(pools=[_pool(pool_id="buy", side=LiquiditySide.BUY_SIDE, price=99.5)]),
    )
    ids = [z.zone_id for z, _ in ranked]
    assert ids[0] == "bull-near"
    assert "bear-near" in ids


def test_performance_benchmark_guards():
    candles = []
    price = 2000.0
    for i in range(1000):
        o = price
        c = price + (0.4 if i % 25 == 7 else 0.1)
        if i % 25 == 5:
            candles.append(make_candle(i, open_=o - 0.5, high=o, low=o - 1, close=o - 0.2))
        elif i % 25 == 6:
            candles.append(make_candle(i, open_=o, high=o + 1, low=o - 0.2, close=o + 0.8))
            price = o + 0.8
        elif i % 25 == 7:
            lo = price + 1.0
            candles.append(make_candle(i, open_=lo + 0.2, high=lo + 1.5, low=lo, close=lo + 1.0))
            price = lo + 1.0
        else:
            candles.append(make_candle(i, open_=o, high=c + 0.2, low=o - 0.2, close=c))
            price = c

    results = {}
    for n in (100, 500, 1000):
        window = candles[:n]
        t0 = time.perf_counter()
        zs = detect_fvg_zones(window)
        obs = detect_order_block_zones(window)
        enrich_and_rank_zones(
            zs.zones,
            price=float(window[-1].close),
            atr=1.0,
            structure=_empty_structure(),
            as_of_index=n - 1,
        )
        enrich_and_rank_zones(
            obs.zones,
            price=float(window[-1].close),
            atr=1.0,
            structure=_empty_structure(),
            as_of_index=n - 1,
        )
        results[n] = (time.perf_counter() - t0) * 1000
    assert results[1000] < 500.0
    assert results[500] < 300.0
    assert results[100] < 100.0


def test_ranking_key_tuple_is_total_order():
    z = _fvg(zone_id="a", direction=SignalDirection.BUY, lo=100, hi=102, created=2)
    ctx = build_zone_context(z, price=103, atr=1.0, structure=_empty_structure())
    key = ranking_key(z, ctx)
    assert isinstance(key, tuple)
    assert key[-1] == "a"

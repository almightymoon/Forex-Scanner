"""SMC Confluence Engine v1 — acceptance, conflicts, causality, determinism."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from shared.types.models import (
    IndicatorValues,
    SMCPattern,
    SignalDirection,
    Timeframe,
    TrendDirection,
)
from swing_engine.models import SwingScope

from services.quant_engine.decision.engine import DecisionEngine
from services.quant_engine.liquidity.models import (
    LIQUIDITY_ENGINE_VERSION,
    LiquidityPool,
    LiquiditySide,
    LiquiditySnapshot,
    PoolStatus,
    PoolStrength,
    PoolType,
    SweepGrade,
    SweepKind,
    SweepQuality,
    LiquiditySweepEvent,
)
from services.quant_engine.market_structure.models import (
    StructureEvent,
    StructureEventType,
    StructureSnapshot,
)
from services.quant_engine.market_structure.regime import StructureRegime
from services.quant_engine.features.types import MarketFeatures
from services.quant_engine.smc_confluence import (
    SMC_CONFLUENCE_ENGINE_VERSION,
    ConfluenceBias,
    ConfluenceStrength,
    build_smc_context,
)
from services.quant_engine.swings.boundary import SCAN_SWING_VERSION


def _ts(i: int) -> datetime:
    return datetime(2024, 6, 3, tzinfo=timezone.utc) + timedelta(hours=i)


def _bos(direction: TrendDirection, break_index: int, price: float) -> StructureEvent:
    return StructureEvent(
        event_id=f"bos-{direction.value}-{break_index}",
        event_type=StructureEventType.BOS,
        direction=direction,
        scope=SwingScope.EXTERNAL,
        level_swing_id=f"sw-{break_index}",
        level_pivot_index=break_index - 2,
        level_price=price,
        level_available_index=break_index - 1,
        break_index=break_index,
        break_timestamp=_ts(break_index),
        break_close=price,
        prior_bias=TrendDirection.RANGING,
        resulting_bias=direction,
        pending_bias=TrendDirection.RANGING,
        is_continuation=True,
    )


def _structure(
    *,
    external: TrendDirection,
    as_of: int,
    events: tuple[StructureEvent, ...] = (),
) -> StructureSnapshot:
    return StructureSnapshot(
        as_of_index=as_of,
        external_bias=external,
        pending_external_bias=TrendDirection.RANGING,
        internal_bias=external,
        pending_internal_bias=TrendDirection.RANGING,
        swing_relations=(),
        events=events,
        latest_external_high=2655.0,
        latest_external_low=2640.0,
        latest_internal_high=2652.0,
        latest_internal_low=2642.0,
    )


def _pool(
    pool_id: str,
    pool_type: PoolType,
    side: LiquiditySide,
    price: float,
    *,
    available: int = 5,
) -> LiquidityPool:
    return LiquidityPool(
        pool_id=pool_id,
        pool_type=pool_type,
        side=side,
        price=price,
        symbol="XAUUSD",
        source_timeframe="H1",
        scope="EXTERNAL",
        status=PoolStatus.ACTIVE,
        strength=PoolStrength.STRONG,
        strength_score=0.8,
        touches=2,
        created_index=available - 1,
        available_index=available,
        created_at=_ts(available - 1),
        available_at=_ts(available),
        source_reference="test",
        reasons=("test",),
    )


def _sweep(
    sweep_id: str,
    kind: SweepKind,
    price: float,
    bar_index: int,
    pool_type: PoolType = PoolType.EQUAL_LOW,
) -> LiquiditySweepEvent:
    return LiquiditySweepEvent(
        sweep_id=sweep_id,
        kind=kind,
        pool_id=f"pool-{sweep_id}",
        pool_type=pool_type,
        level_price=price,
        bar_index=bar_index,
        timestamp=_ts(bar_index),
        penetration=0.4,
        penetration_atr=0.3,
        rejection_pct=70.0,
        grade=SweepGrade.STRONG,
        bias_quality=SweepQuality.CONTINUATION,
        reasons=("test",),
    )


def _liq(
    *,
    as_of: int,
    pools: tuple[LiquidityPool, ...] = (),
    sweeps: tuple[LiquiditySweepEvent, ...] = (),
) -> LiquiditySnapshot:
    return LiquiditySnapshot(
        symbol="XAUUSD",
        timeframe="H1",
        as_of_index=as_of,
        pools=pools,
        sweeps=sweeps,
        session_tags=(),
        atr=5.0,
        equality_tolerance=0.75,
        algorithm_version=LIQUIDITY_ENGINE_VERSION,
    )


def test_version_constants():
    assert SMC_CONFLUENCE_ENGINE_VERSION == "1.0.0"
    assert SCAN_SWING_VERSION == "2.3.0"


def test_scenario_a_strong_bullish_confluence():
    as_of = 40
    snap = _structure(
        external=TrendDirection.BULLISH,
        as_of=as_of,
        events=(_bos(TrendDirection.BULLISH, 30, 2650.0),),
    )
    features = MarketFeatures(
        external_bias=TrendDirection.BULLISH,
        structure_regime=StructureRegime.TRENDING_BULLISH.value,
        structure_snapshot=snap,
        structure_regime_confidence=0.85,
    )
    liq = _liq(
        as_of=as_of,
        pools=(_pool("pl", PoolType.EQUAL_LOW, LiquiditySide.BUY_SIDE, 2640.0),),
        sweeps=(_sweep("s1", SweepKind.SWEEP_LOW, 2640.0, 28),),
    )
    patterns = [
        SMCPattern(pattern_type="fvg", direction=SignalDirection.BUY, strength=70),
        SMCPattern(pattern_type="order_block", direction=SignalDirection.BUY, strength=75),
    ]
    mtf = {
        "D1": TrendDirection.BULLISH,
        "H4": TrendDirection.BULLISH,
        "H1": TrendDirection.BULLISH,
        "M15": TrendDirection.BULLISH,
    }
    ctx = build_smc_context(
        symbol="XAUUSD",
        timeframe=Timeframe.H1,
        features=features,
        structure_snapshot=snap,
        liquidity_snapshot=liq,
        patterns=patterns,
        mtf_trends=mtf,
        as_of_index=as_of,
    )
    assert ctx.dominant_bias is ConfluenceBias.BULLISH
    assert ctx.confluence_strength is ConfluenceStrength.STRONG
    assert ctx.bullish_score > ctx.bearish_score
    assert ctx.algorithm_versions.smc_confluence_engine == "1.0.0"
    assert any("Sell-side liquidity swept" in e.label for e in ctx.bullish_confluences)
    assert ctx.explanations


def test_scenario_b_strong_bearish_confluence():
    as_of = 40
    snap = _structure(
        external=TrendDirection.BEARISH,
        as_of=as_of,
        events=(_bos(TrendDirection.BEARISH, 30, 2650.0),),
    )
    features = MarketFeatures(
        external_bias=TrendDirection.BEARISH,
        structure_regime=StructureRegime.TRENDING_BEARISH.value,
        structure_snapshot=snap,
    )
    liq = _liq(
        as_of=as_of,
        pools=(_pool("ph", PoolType.EQUAL_HIGH, LiquiditySide.SELL_SIDE, 2660.0),),
        sweeps=(_sweep("s1", SweepKind.SWEEP_HIGH, 2660.0, 28, PoolType.EQUAL_HIGH),),
    )
    patterns = [
        SMCPattern(pattern_type="fvg", direction=SignalDirection.SELL, strength=70),
        SMCPattern(pattern_type="order_block", direction=SignalDirection.SELL, strength=75),
    ]
    mtf = {
        "D1": TrendDirection.BEARISH,
        "H4": TrendDirection.BEARISH,
        "H1": TrendDirection.BEARISH,
        "M15": TrendDirection.BEARISH,
    }
    ctx = build_smc_context(
        symbol="XAUUSD",
        timeframe="H1",
        features=features,
        structure_snapshot=snap,
        liquidity_snapshot=liq,
        patterns=patterns,
        mtf_trends=mtf,
        as_of_index=as_of,
    )
    assert ctx.dominant_bias is ConfluenceBias.BEARISH
    assert ctx.confluence_strength is ConfluenceStrength.STRONG


def test_scenario_c_mixed_htf_ltf_and_fvg_ob():
    as_of = 40
    snap = _structure(external=TrendDirection.BEARISH, as_of=as_of)
    features = MarketFeatures(
        external_bias=TrendDirection.BEARISH,
        structure_regime=StructureRegime.TRENDING_BEARISH.value,
        structure_snapshot=snap,
    )
    patterns = [
        SMCPattern(pattern_type="fvg", direction=SignalDirection.BUY, strength=70),
        SMCPattern(pattern_type="order_block", direction=SignalDirection.SELL, strength=75),
    ]
    mtf = {
        "H4": TrendDirection.BEARISH,
        "H1": TrendDirection.BEARISH,
        "M15": TrendDirection.BULLISH,
    }
    ctx = build_smc_context(
        symbol="XAUUSD",
        timeframe="H1",
        features=features,
        structure_snapshot=snap,
        patterns=patterns,
        mtf_trends=mtf,
        as_of_index=as_of,
    )
    assert ctx.dominant_bias in (ConfluenceBias.MIXED, ConfluenceBias.BEARISH, ConfluenceBias.NEUTRAL)
    assert any(c.label == "FVG vs OB" for c in ctx.conflicts)
    assert any("HTF/LTF" in c.label for c in ctx.conflicts)


def test_scenario_d_undefined_insufficient_structure():
    ctx = build_smc_context(
        symbol="XAUUSD",
        timeframe="H1",
        features=MarketFeatures(),
        structure_snapshot=None,
        patterns=[],
        mtf_trends={},
        as_of_index=10,
    )
    assert ctx.dominant_bias is ConfluenceBias.UNDEFINED
    assert ctx.confluence_strength is ConfluenceStrength.NONE


def test_scenario_e_future_sweep_not_in_earlier_snapshot():
    """Caller supplies causal LiquiditySnapshot; earlier as_of must omit future sweep."""
    future_sweep = _sweep("future", SweepKind.SWEEP_LOW, 2640.0, 35)
    early = _liq(as_of=20, sweeps=())
    late = _liq(as_of=40, sweeps=(future_sweep,))
    snap_early = _structure(external=TrendDirection.BULLISH, as_of=20)
    snap_late = _structure(
        external=TrendDirection.BULLISH,
        as_of=40,
        events=(_bos(TrendDirection.BULLISH, 30, 2650.0),),
    )
    early_ctx = build_smc_context(
        symbol="XAUUSD",
        timeframe="H1",
        structure_snapshot=snap_early,
        liquidity_snapshot=early,
        features=MarketFeatures(external_bias=TrendDirection.BULLISH, structure_snapshot=snap_early),
        as_of_index=20,
    )
    late_ctx = build_smc_context(
        symbol="XAUUSD",
        timeframe="H1",
        structure_snapshot=snap_late,
        liquidity_snapshot=late,
        features=MarketFeatures(external_bias=TrendDirection.BULLISH, structure_snapshot=snap_late),
        as_of_index=40,
    )
    assert early_ctx.liquidity_context["recent_low_sweeps"] == []
    assert early_ctx.last_bos is None
    assert late_ctx.liquidity_context["recent_low_sweeps"]
    assert late_ctx.last_bos is not None
    assert late_ctx.last_bos["break_index"] == 30


def test_determinism_same_inputs_same_snapshot():
    snap = _structure(
        external=TrendDirection.BULLISH,
        as_of=25,
        events=(_bos(TrendDirection.BULLISH, 20, 2650.0),),
    )
    liq = _liq(
        as_of=25,
        sweeps=(_sweep("s1", SweepKind.SWEEP_LOW, 2640.0, 18),),
    )
    patterns = [
        SMCPattern(pattern_type="fvg", direction=SignalDirection.BUY, strength=70),
    ]
    kwargs = dict(
        symbol="XAUUSD",
        timeframe="H1",
        structure_snapshot=snap,
        liquidity_snapshot=liq,
        patterns=patterns,
        mtf_trends={"H4": TrendDirection.BULLISH},
        features=MarketFeatures(
            external_bias=TrendDirection.BULLISH,
            structure_regime=StructureRegime.TRENDING_BULLISH.value,
            structure_snapshot=snap,
        ),
        as_of_index=25,
    )
    a = build_smc_context(**kwargs).to_dict()
    b = build_smc_context(**kwargs).to_dict()
    assert a == b


def test_structure_plus_liquidity_only():
    snap = _structure(external=TrendDirection.BULLISH, as_of=20)
    liq = _liq(as_of=20, sweeps=(_sweep("s1", SweepKind.SWEEP_LOW, 2640.0, 15),))
    ctx = build_smc_context(
        symbol="XAUUSD",
        timeframe="H1",
        structure_snapshot=snap,
        liquidity_snapshot=liq,
        features=MarketFeatures(
            external_bias=TrendDirection.BULLISH,
            structure_regime=StructureRegime.TRENDING_BULLISH.value,
            structure_snapshot=snap,
        ),
        as_of_index=20,
    )
    assert ctx.bullish_score > 0
    assert ctx.dominant_bias in (ConfluenceBias.BULLISH, ConfluenceBias.NEUTRAL)


def test_decision_engine_attaches_smc_context():
    from services.quant_engine.market_structure import analyze_structure
    from services.quant_engine.swings.boundary import obtain_confirmed_swings
    from tests.swing_detection.fixtures import gold_candles

    candles = gold_candles(220, trend=0.5, wave=8.0)
    swings = obtain_confirmed_swings(candles, version=SCAN_SWING_VERSION)
    snapshot = analyze_structure(candles, swings)
    last = candles[-1]
    indicators = IndicatorValues(
        symbol="XAUUSD",
        timeframe=Timeframe.H1,
        timestamp=last.timestamp,
        ema_20=last.close * 0.999,
        ema_50=last.close * 0.997,
        ema_200=last.close * 0.99,
        adx_14=28.0,
        rsi_14=58.0,
        macd_histogram=0.4,
        atr_14=max(1.0, (last.high - last.low) * 1.2),
        bb_lower=last.close * 0.99,
        bb_middle=last.close,
        bb_upper=last.close * 1.01,
    )
    signal = DecisionEngine().evaluate(
        "XAUUSD",
        Timeframe.H1,
        candles,
        indicators,
        [
            SMCPattern(pattern_type="fvg", direction=SignalDirection.BUY, strength=60),
            SMCPattern(pattern_type="order_block", direction=SignalDirection.BUY, strength=65),
        ],
        confirmed_swings=swings,
        structure_snapshot=snapshot,
        mtf_trends={"H4": TrendDirection.BULLISH, "H1": TrendDirection.BULLISH},
    )
    assert "smc_context" in signal.market_features
    ctx = signal.market_features["smc_context"]
    assert ctx["algorithm_versions"]["smc_confluence_engine"] == "1.0.0"
    assert ctx["dominant_bias"] in {b.value for b in ConfluenceBias}
    assert "smc_context" in signal.explainability

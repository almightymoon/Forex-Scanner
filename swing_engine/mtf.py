"""Multi-timeframe swing hierarchy (Sprint 4).

Builds institutional structure context so every lower-TF swing knows its parent:

    D1 → H4 → H1 → M15 → M5

Each LTF swing receives parent swing, trend, external range, and liquidity levels
from the nearest HTF structure. This is the backbone for BOS and CHoCH.
"""

from __future__ import annotations

from shared.types.models import Candle, Timeframe

from swing_engine.config import SwingEngineConfig, get_config
from swing_engine.detector import SwingEngine
from swing_engine.models import (
    DetectedSwing,
    MTFHierarchyResult,
    MTFSwingContext,
    SwingDirection,
    SwingScope,
    TrendBias,
)

# Default institutional hierarchy (highest TF first).
DEFAULT_HIERARCHY = ["D1", "H4", "H1", "M15", "M5", "M1"]


def detect_mtf_hierarchy(
    bars_by_timeframe: dict[str, list[Candle]],
    *,
    symbol: str,
    version: str = "1.3.0",
    hierarchy: list[str] | None = None,
    config: SwingEngineConfig | None = None,
) -> MTFHierarchyResult:
    """Detect swings per TF and attach parent context bottom-up."""
    order = hierarchy or DEFAULT_HIERARCHY
    present = [tf for tf in order if tf in bars_by_timeframe and bars_by_timeframe[tf]]
    if not present:
        return MTFHierarchyResult(symbol=symbol, hierarchy=order, swings_by_timeframe={}, contexts={})

    engine = SwingEngine(config, version=version) if config else SwingEngine(version=version)
    swings_by_tf: dict[str, list[DetectedSwing]] = {}
    contexts: dict[str, MTFSwingContext] = {}

    for tf_name in present:
        tf = Timeframe(tf_name)
        cfg = config or get_config(tf, version=version, symbol=symbol)
        result = engine.detect(bars_by_timeframe[tf_name], symbol=symbol, timeframe=tf, config=cfg)
        swings_by_tf[tf_name] = result.swings

    # Map each swing to parent TF (next higher in hierarchy).
    for i, tf_name in enumerate(present):
        parent_tf = present[i - 1] if i > 0 else None
        parent_swings = swings_by_tf.get(parent_tf, []) if parent_tf else []
        parent_trend = _infer_trend(parent_swings)

        for swing in swings_by_tf[tf_name]:
            ctx = _build_parent_context(swing, parent_tf, parent_swings, parent_trend)
            swing.mtf_context = ctx
            key = f"{tf_name}:{swing.pivot_index}:{swing.direction.value}"
            contexts[key] = ctx

    return MTFHierarchyResult(
        symbol=symbol,
        hierarchy=order,
        swings_by_timeframe=swings_by_tf,
        contexts=contexts,
    )


def _infer_trend(swings: list[DetectedSwing]) -> TrendBias:
    if len(swings) < 2:
        return TrendBias.RANGING
    highs = [s for s in swings if s.direction == SwingDirection.HIGH]
    lows = [s for s in swings if s.direction == SwingDirection.LOW]
    if len(highs) >= 2 and len(lows) >= 2:
        hh = highs[-1].price > highs[-2].price
        hl = lows[-1].price > lows[-2].price
        lh = highs[-1].price < highs[-2].price
        ll = lows[-1].price < lows[-2].price
        if hh and hl:
            return TrendBias.BULLISH
        if lh and ll:
            return TrendBias.BEARISH
    return TrendBias.RANGING


def _build_parent_context(
    swing: DetectedSwing,
    parent_tf: str | None,
    parent_swings: list[DetectedSwing],
    parent_trend: TrendBias,
) -> MTFSwingContext:
    if not parent_tf:
        return MTFSwingContext(parent_trend=parent_trend)
    if not parent_swings:
        return MTFSwingContext(parent_timeframe=parent_tf, parent_trend=parent_trend)

    parent = _nearest_parent_swing(swing, parent_swings)
    ext_highs = [s.price for s in parent_swings if s.direction == SwingDirection.HIGH and s.scope == SwingScope.EXTERNAL]
    ext_lows = [s.price for s in parent_swings if s.direction == SwingDirection.LOW and s.scope == SwingScope.EXTERNAL]
    all_highs = [s.price for s in parent_swings if s.direction == SwingDirection.HIGH]
    all_lows = [s.price for s in parent_swings if s.direction == SwingDirection.LOW]

    ext_hi = max(ext_highs) if ext_highs else (max(all_highs) if all_highs else None)
    ext_lo = min(ext_lows) if ext_lows else (min(all_lows) if all_lows else None)
    dealing = (ext_lo, ext_hi) if ext_lo is not None and ext_hi is not None else None

    alignment = _alignment_score(swing, parent_trend, ext_hi, ext_lo)

    return MTFSwingContext(
        parent_timeframe=parent_tf,
        parent_swing_id=f"{parent.direction.value}:{parent.pivot_index}" if parent else None,
        parent_trend=parent_trend,
        parent_external_high=ext_hi,
        parent_external_low=ext_lo,
        parent_dealing_range=dealing,
        parent_liquidity_high=ext_hi,
        parent_liquidity_low=ext_lo,
        alignment_score=alignment,
    )


def _nearest_parent_swing(swing: DetectedSwing, parent_swings: list[DetectedSwing]) -> DetectedSwing | None:
    prior = [s for s in parent_swings if s.pivot_index <= swing.pivot_index]
    if not prior:
        return parent_swings[0] if parent_swings else None
    return prior[-1]


def _alignment_score(
    swing: DetectedSwing,
    trend: TrendBias,
    ext_hi: float | None,
    ext_lo: float | None,
) -> float:
    score = 0.5
    if trend == TrendBias.BULLISH and swing.direction == SwingDirection.LOW:
        score += 0.25
    elif trend == TrendBias.BEARISH and swing.direction == SwingDirection.HIGH:
        score += 0.25
    elif trend == TrendBias.RANGING:
        score += 0.1
    if ext_hi is not None and ext_lo is not None:
        mid = (ext_hi + ext_lo) / 2
        if swing.direction == SwingDirection.HIGH and swing.price > mid:
            score += 0.15
        elif swing.direction == SwingDirection.LOW and swing.price < mid:
            score += 0.15
    return min(1.0, score)

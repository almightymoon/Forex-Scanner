"""Adaptive market-context detection (Sprint 3, Priority 1).

Computes a :class:`MarketContext` snapshot (volatility regime, structure
regime, trading session, spread) from the incoming bars and adapts the static
:class:`SwingEngineConfig` thresholds to the current conditions.

This module only *reads* bars and *scales* thresholds — it never implements
detection logic itself. The detector behaves differently in a quiet Asian
session than during the London–New York overlap.
"""

from __future__ import annotations

import dataclasses

from shared.types.models import Candle

from swing_engine.config import SwingEngineConfig
from swing_engine.models import (
    MarketContext,
    StructureRegime,
    TradingSession,
    VolatilityRegime,
)


def _percentile_rank(values: list[float], target: float) -> float:
    if not values:
        return 50.0
    below = sum(1 for v in values if v <= target)
    return 100.0 * below / len(values)


def _efficiency_ratio(candles: list[Candle], window: int) -> float:
    """Kaufman Efficiency Ratio over the trailing window (0=choppy, 1=trending)."""
    if len(candles) < 2:
        return 0.0
    seg = candles[-window:] if window > 0 else candles
    if len(seg) < 2:
        return 0.0
    net = abs(seg[-1].close - seg[0].close)
    path = sum(abs(seg[i].close - seg[i - 1].close) for i in range(1, len(seg)))
    return net / path if path > 0 else 0.0


def _session(candle: Candle) -> TradingSession:
    """Classify session by UTC hour. Overlap = London+NY (12:00-16:00 UTC)."""
    hour = candle.timestamp.hour
    if 12 <= hour < 16:
        return TradingSession.OVERLAP
    if 7 <= hour < 16:
        return TradingSession.LONDON
    if 13 <= hour < 21:
        return TradingSession.NEW_YORK
    if 0 <= hour < 9:
        return TradingSession.ASIA
    return TradingSession.OFF


def compute_market_context(
    candles: list[Candle],
    atr_series: list[float],
    config: SwingEngineConfig,
) -> MarketContext:
    if not candles or not atr_series:
        return MarketContext()

    adp = config.adaptive
    current_atr = atr_series[-1] if atr_series[-1] > 0 else 1e-9
    window = atr_series[-adp.atr_percentile_window:] if adp.atr_percentile_window > 0 else atr_series
    window = [a for a in window if a > 0]
    pct = _percentile_rank(window, current_atr)

    if pct >= adp.high_volatility_percentile:
        vol = VolatilityRegime.HIGH
    elif pct <= adp.low_volatility_percentile:
        vol = VolatilityRegime.LOW
    else:
        vol = VolatilityRegime.NORMAL

    er = _efficiency_ratio(candles, adp.efficiency_window)
    structure = StructureRegime.TRENDING if er >= adp.trending_efficiency_min else StructureRegime.RANGING

    session = _session(candles[-1]) if adp.session_enabled else TradingSession.OFF

    last = candles[-1]
    spread = last.high - last.low
    spread_atr = spread / current_atr if current_atr > 0 else 0.0

    return MarketContext(
        volatility_regime=vol,
        structure_regime=structure,
        session=session,
        atr_percentile=pct,
        efficiency_ratio=er,
        spread_atr_ratio=spread_atr,
        current_atr=current_atr,
    )


def adapt_config(config: SwingEngineConfig, context: MarketContext) -> SwingEngineConfig:
    """Return a new config whose thresholds are scaled to the market context.

    Uses :func:`dataclasses.replace` so the base config is never mutated.
    """
    adp = config.adaptive
    if not adp.enabled:
        return config

    nf = config.noise_filter
    leg = config.leg
    pivot = config.pivot
    conf = config.confirmation
    clf = config.classification

    pip_mult = 1.0
    leg_atr_mult = 1.0
    pivot_strength_add = 0.0
    major_atr_mult = 1.0
    min_atr_mult = 1.0
    delay_add = 0

    # Volatility scaling.
    if context.volatility_regime == VolatilityRegime.HIGH:
        pip_mult *= adp.high_vol_pip_distance_mult
        major_atr_mult *= adp.high_vol_major_atr_mult
    elif context.volatility_regime == VolatilityRegime.LOW:
        pip_mult *= adp.low_vol_pip_distance_mult
        min_atr_mult *= adp.low_vol_min_atr_mult

    # Structure scaling.
    if context.structure_regime == StructureRegime.RANGING:
        leg_atr_mult *= adp.ranging_leg_atr_mult
        pivot_strength_add += adp.ranging_pivot_strength_add
    else:
        leg_atr_mult *= adp.trending_leg_atr_mult

    # Session scaling.
    if context.session == TradingSession.ASIA:
        pip_mult *= adp.asia_min_pip_mult
        delay_add += adp.asia_delay_add
    elif context.session == TradingSession.OVERLAP:
        pip_mult *= adp.overlap_min_pip_mult

    new_noise = dataclasses.replace(
        nf,
        min_pip_distance=nf.min_pip_distance * pip_mult,
        min_atr_multiple=nf.min_atr_multiple * min_atr_mult,
    )
    new_leg = dataclasses.replace(
        leg,
        min_pips=leg.min_pips * pip_mult,
        min_atr_multiple=leg.min_atr_multiple * leg_atr_mult,
    )
    new_pivot = dataclasses.replace(
        pivot,
        min_pivot_strength=pivot.min_pivot_strength + pivot_strength_add,
    )
    new_conf = dataclasses.replace(conf, delay_bars=conf.delay_bars + delay_add)
    new_clf = dataclasses.replace(
        clf,
        major_min_atr_multiple=clf.major_min_atr_multiple * major_atr_mult,
    )

    return dataclasses.replace(
        config,
        noise_filter=new_noise,
        leg=new_leg,
        pivot=new_pivot,
        confirmation=new_conf,
        classification=new_clf,
    )

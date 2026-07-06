"""Noise filters — remove insignificant swings before scoring."""

from __future__ import annotations

from services.quant_engine.swing.config import NoiseFilterConfig, SwingConfig
from services.quant_engine.swing.models import Swing, SwingSide, SwingTier


def filter_equal_levels(
    swings: list[Swing],
    atr_at_index: list[float],
    config: NoiseFilterConfig,
) -> list[Swing]:
    """Drop repeated equal highs/lows within ATR tolerance."""
    if not config.enabled or len(swings) < 2:
        return swings

    tol_base = config.equal_level_tolerance_atr
    kept: list[Swing] = []
    side_counts: dict[tuple[SwingSide, int], int] = {}

    for swing in swings:
        atr = atr_at_index[swing.index] if swing.index < len(atr_at_index) else 1.0
        tol = tol_base * atr * config.sensitivity
        bucket = round(swing.price / max(tol, 1e-9))
        key = (swing.side, bucket)
        count = side_counts.get(key, 0)

        if count >= config.max_equal_level_repeats:
            continue

        if kept and kept[-1].side == swing.side:
            prev = kept[-1]
            prev_atr = atr_at_index[prev.index] if prev.index < len(atr_at_index) else atr
            if abs(swing.price - prev.price) <= tol_base * prev_atr:
                if swing.side == SwingSide.HIGH and swing.price > prev.price:
                    kept[-1] = swing
                elif swing.side == SwingSide.LOW and swing.price < prev.price:
                    kept[-1] = swing
                continue

        side_counts[key] = count + 1
        kept.append(swing)

    return kept


def filter_micro_swings(swings: list[Swing], config: SwingConfig) -> list[Swing]:
    """Remove swings below minimum strength after scoring pass."""
    nf = config.noise_filter
    if not nf.enabled:
        return swings
    threshold = max(config.minimum_strength, nf.micro_swing_strength / nf.sensitivity)
    return [s for s in swings if s.strength >= threshold or s.tier == SwingTier.MAJOR]


def filter_low_atr_displacement(
    swings: list[Swing],
    atr_at_index: list[float],
    config: SwingConfig,
) -> list[Swing]:
    """Remove swings with displacement below ATR minimum vs previous opposite swing."""
    if not config.noise_filter.enabled or len(swings) < 2:
        return swings

    min_move = config.effective_min_distance()
    kept: list[Swing] = [swings[0]]
    for swing in swings[1:]:
        prev = kept[-1]
        if prev.side == swing.side:
            kept.append(swing)
            continue
        atr = atr_at_index[swing.index] if swing.index < len(atr_at_index) else 1.0
        disp = abs(swing.price - prev.price) / max(atr, 1e-9)
        if disp >= min_move:
            kept.append(swing)
    return kept


def filter_sideways_micro_structure(
    swings: list[Swing],
    atr_at_index: list[float],
    config: NoiseFilterConfig,
) -> list[Swing]:
    """Collapse swings inside a tight sideways range."""
    if not config.enabled or len(swings) < 4:
        return swings

    window = swings[-4:]
    prices = [s.price for s in window]
    idx = window[-1].index
    atr = atr_at_index[idx] if idx < len(atr_at_index) else 1.0
    price_range = max(prices) - min(prices)

    if price_range > config.sideways_range_atr * atr:
        return swings

    majors = [s for s in swings if s.tier == SwingTier.MAJOR]
    if len(majors) >= 2:
        return majors
    return swings


def apply_noise_filters(
    swings: list[Swing],
    atr_at_index: list[float],
    config: SwingConfig,
) -> list[Swing]:
    """Run full noise filter pipeline in deterministic order."""
    nf = config.noise_filter
    if not nf.enabled:
        return swings

    result = filter_equal_levels(swings, atr_at_index, nf)
    result = filter_low_atr_displacement(result, atr_at_index, config)
    result = filter_micro_swings(result, config)
    result = filter_sideways_micro_structure(result, atr_at_index, nf)
    return result

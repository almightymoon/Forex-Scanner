"""Shared confirmed-swing boundary for the live scan / feature path.

Decision (explicit cutover):
    SCAN_SWING_VERSION = \"2.3.0\"

Rationale:
- Aligns the live scan boundary with the architecture production candidate.
- Does **not** change ``swing_engine.DEFAULT_VERSION`` (still ``2.0.0`` unless
  callers omit ``version=``).
- Callers must pass an explicit version through :func:`obtain_confirmed_swings`.
- Synthetic EURUSD micro-wave fixtures may yield zero confirmed swings under
  2.3.0; integration tests should use gold/synthetic XAUUSD fixtures or inject
  confirmed swings.
"""

from __future__ import annotations

from shared.types.models import Candle
from swing_engine import SwingEngine, get_config
from swing_engine.models import DetectedSwing, SwingScope, SwingTier

# Live scan / feature boundary version (explicit 2.3.0 cutover).
SCAN_SWING_VERSION = "2.3.0"

# Backward-compatible alias used by FeatureExtractor.
FEATURE_SWING_VERSION = SCAN_SWING_VERSION


def dedupe_confirmed_swings(
    swings: list[DetectedSwing],
) -> list[DetectedSwing]:
    """Keep one swing per (direction, pivot_index).

    Prefers EXTERNAL over INTERNAL and MAJOR over MINOR when the engine emits
    conflicting labels for the same pivot identity.
    """

    best: dict[tuple[str, int], DetectedSwing] = {}

    def _rank(swing: DetectedSwing) -> tuple[int, int, int]:
        scope_rank = 2 if swing.scope is SwingScope.EXTERNAL else (
            1 if swing.scope is SwingScope.INTERNAL else 0
        )
        tier_rank = 1 if swing.tier is SwingTier.MAJOR else 0
        hier = (
            int(swing.hierarchy_confirmation_index)
            if swing.hierarchy_confirmation_index is not None
            else -1
        )
        return (scope_rank, tier_rank, hier)

    for swing in swings:
        key = (swing.direction.value, int(swing.pivot_index))
        prior = best.get(key)
        if prior is None or _rank(swing) > _rank(prior):
            best[key] = swing
    return list(best.values())


def obtain_confirmed_swings(
    candles: list[Candle],
    *,
    version: str = SCAN_SWING_VERSION,
) -> list[DetectedSwing]:
    """Run SwingEngine once and return ``result.confirmed_swings`` only."""

    if not candles:
        return []
    tf = candles[0].timeframe
    symbol = candles[0].symbol
    cfg = get_config(tf, version=version, symbol=symbol)
    result = SwingEngine(cfg, version=version).detect(
        candles,
        symbol=symbol,
        timeframe=tf,
    )
    return dedupe_confirmed_swings(list(result.confirmed_swings))

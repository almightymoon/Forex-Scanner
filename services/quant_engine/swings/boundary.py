"""Shared confirmed-swing boundary for the live scan / feature path.

Decision (deliberate, documented):
    SCAN_SWING_VERSION = \"2.0.0\"

Rationale:
- Matches ``swing_engine.DEFAULT_VERSION`` and the scanner's current live path.
- Does **not** change the repository-wide default.
- v2.3.0 remains the architecture production candidate, but an explicit cutover
  is deferred: on existing EURUSD synthetic fixtures v2.3 returns zero confirmed
  swings without parameter tuning (out of scope here).

Callers must obtain confirmed swings through :func:`obtain_confirmed_swings`
rather than instantiating ad-hoc SwingEngine configs inside SMC or structure
scoring.
"""

from __future__ import annotations

from shared.types.models import Candle
from swing_engine import SwingEngine, get_config
from swing_engine.models import DetectedSwing, SwingScope, SwingTier

# Live scan / feature boundary version. Upgrade only via an explicit task.
SCAN_SWING_VERSION = "2.0.0"

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

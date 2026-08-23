"""Shared confirmed-swing boundary for the live scan / feature path.

Decision (explicit cutover — already landed):
    SCAN_SWING_VERSION = \"2.3.0\"
    FEATURE_SWING_VERSION = SCAN_SWING_VERSION
    swing_engine.DEFAULT_VERSION = \"2.3.0\"

Rationale:
- Aligns the live scan boundary and the engine default with the architecture
  production candidate (v2.3.0).
- Callers may still pass an explicit older version through
  :func:`obtain_confirmed_swings` or ``SwingEngine(version=...)``.
- Synthetic EURUSD micro-wave fixtures may yield zero confirmed swings under
  2.3.0; integration tests should use gold/synthetic XAUUSD fixtures or inject
  confirmed swings.

Canonical scan contract:
    :class:`ScanStructureInput` — candles + confirmed swings + version, then
    one :func:`analyze_structure` for the remainder of the scan.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from shared.types.models import Candle
from swing_engine import SwingEngine, get_config
from swing_engine.models import DetectedSwing, SwingScope, SwingTier

if TYPE_CHECKING:
    from services.quant_engine.market_structure.models import StructureSnapshot

# Live scan / feature boundary version (explicit 2.3.0 cutover).
SCAN_SWING_VERSION = "2.3.0"

# Backward-compatible alias used by FeatureExtractor.
FEATURE_SWING_VERSION = SCAN_SWING_VERSION


@dataclass(frozen=True)
class ScanStructureInput:
    """Canonical structure inputs for one scan (single swing pass).

    Downstream consumers (FeatureExtractor, SMC, TrendEngine,
    MarketStructureEngine scoring) must receive these objects rather than
    rediscovering pivots.
    """

    candles: tuple[Candle, ...]
    confirmed_swings: tuple[DetectedSwing, ...]
    swing_version: str
    structure_snapshot: StructureSnapshot | None = None

    def __post_init__(self) -> None:
        if not self.swing_version or not str(self.swing_version).strip():
            raise ValueError(
                "swing_version must be an explicit non-empty version string"
            )


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
    if not version or not str(version).strip():
        raise ValueError("version must be an explicit non-empty string")
    tf = candles[0].timeframe
    symbol = candles[0].symbol
    cfg = get_config(tf, version=version, symbol=symbol)
    result = SwingEngine(cfg, version=version).detect(
        candles,
        symbol=symbol,
        timeframe=tf,
    )
    return dedupe_confirmed_swings(list(result.confirmed_swings))


def build_scan_structure(
    candles: list[Candle],
    *,
    version: str = SCAN_SWING_VERSION,
    as_of_index: int | None = None,
) -> ScanStructureInput:
    """Canonical producer: one confirmed-swing pass + one structure analysis.

    Market Structure detector is imported lazily to avoid an import-time cycle:
    boundary → market_structure → engine → features → extractor → boundary.
    """

    from services.quant_engine.market_structure.detector import analyze_structure

    swings = obtain_confirmed_swings(candles, version=version)
    snapshot = analyze_structure(candles, swings, as_of_index=as_of_index)
    return ScanStructureInput(
        candles=tuple(candles),
        confirmed_swings=tuple(swings),
        swing_version=version,
        structure_snapshot=snapshot,
    )

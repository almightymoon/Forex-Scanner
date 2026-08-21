"""Market Structure Engine v1 — core contract.

DEVELOPMENT_ONLY documentation for the causal structure detector.
"""

# Purpose

Consume **confirmed swings** from the swing engine and emit deterministic
structure relations and BOS/CHoCH events. The detector does not discover
pivots, does not instantiate `SwingEngine`, and does not call `get_config`.

# Entry point

```python
from services.quant_engine.market_structure import analyze_structure

snapshot = analyze_structure(
    candles,
    result.confirmed_swings,  # never result.swings
    as_of_index=len(candles) - 1,
)
```

# DetectedSwing hierarchy lifecycle (v2.2+ / v2.3)

- First-level confirmation freezes pivot / price / direction at
  `confirmation_index`. Hierarchy reset leaves the swing MINOR / INTERNAL.
- `hierarchy_confirmation_index` is set only when a later opposite confirmed
  swing promotes the pivot to `CONFIRMED_MAJOR` (MAJOR + EXTERNAL under
  `major_external` policy).
- `PROVISIONAL_MAJOR` has no `hierarchy_confirmation_index` and is not a frozen
  external anchor.

# Causal projection (monotonic availability)

`project_swing_facts(swing)` emits fixed facts whose `available_index` never
changes when `as_of_index` increases:

1. **First-level fact** — always available at `confirmation_index`.
   If `hierarchy_confirmation_index` is set, this fact is INTERNAL / MINOR
   even when the final `DetectedSwing` labels are EXTERNAL / MAJOR.
2. **Hierarchy external fact** — when `hierarchy_confirmation_index` is set,
   a second EXTERNAL / MAJOR fact becomes available exactly at that index.
   Earlier INTERNAL history is retained (not rewritten or erased).
3. **Supplied external** — when hierarchy confirmation is absent and the
   caller already labeled EXTERNAL / MAJOR, a single external fact is
   available at `confirmation_index` (no delayed promotion in the input).
4. Otherwise a single INTERNAL fact is available at `confirmation_index`.

`structural_available_index(swing)` returns only the first-level
`confirmation_index` and does **not** take `as_of_index`.

Callers include a fact only when `available_index <= as_of_index`.

# Relations (same direction + same scope track)

Highs: HH / LH / EQUAL_HIGH  
Lows: HL / LL / EQUAL_LOW  

Equality uses `StructureDetectorConfig.price_equality_tolerance`.

EXTERNAL and INTERNAL tracks are separate: an internal high is never compared
directly to an external high for relation assignment.

# Break rule (v1)

- A level activates at `available_index` but may break only when
  `break_index > level_available_index` (same-candle activation/break forbidden).
- Bullish break: candle **close** strictly above an active high level
- Bearish break: candle **close** strictly below an active low level
- Wick-only crossings do **not** count
- Each level emits at most one break event

# Atomic multi-level breaks (per scope, per candle)

1. Gather all newly crossed bullish highs and bearish lows.
2. Mark every crossed level broken (retired).
3. Representative bullish level = highest crossed high; bearish = lowest crossed low.
4. Emit at most one bullish and one bearish transition.
5. Processing order: bullish group, then bearish group.
6. A CHOCH may not be confirmed by BOS at the same `break_index`; pending
   reversal confirmation requires a later candle.

# External state machine

- Neutral: first break → BOS and sets bias
- With bias: same-direction break → continuation BOS
- Opposite break → CHOCH; sets **pending** opposite bias; confirmed bias
  unchanged
- While pending: opposite-direction break → confirming BOS; same-direction
  break cancels pending and emits continuation BOS

Internal track mirrors the same machine but never mutates external bias.

# Causality

No event depends on candles after its `break_index` / `as_of_index`.

# Legacy scoring warning

`score_structure_event` in `market_structure/scoring.py` uses forward candles
for follow-through. That dimension is offline / lookahead-sensitive and must
**not** be used for live event confirmation until separately refactored. The
v1 detector does not call it.

# Production wiring

FeatureExtractor obtains confirmed swings once at the integration boundary
(explicit `swing_version="2.3.0"`, or injected `confirmed_swings`) and calls
`analyze_structure`. It does not use legacy `build_zigzag_swings` /
`analyze_market_structure` for structure fields.

Adapter: `services/quant_engine/market_structure/integration.py`
(`structure_snapshot_to_features`).

TrendEngine scores HH/HL/LH/LL from the v1 snapshot relations, not a raw
ten-candle half-split heuristic.

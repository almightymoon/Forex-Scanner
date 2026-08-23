# Liquidity Engine v1

Deterministic liquidity pools and sweeps on top of Market Structure Engine v1.

Package: `services/quant_engine/liquidity/`  
Algorithm version: **`1.0.0`** (`LIQUIDITY_ENGINE_VERSION`)

Does **not** decide BUY/SELL. Decision Engine consumes the snapshot.

---

## Architecture

```text
Candles + StructureSnapshot (+ optional SMC patterns)
        ↓
analyze_liquidity(...)
        ↓
LiquiditySnapshot
   ├── pools (EQUAL / STRUCTURAL / SESSION)
   ├── sweeps (SWEEP_* / BREAKOUT)
   └── legacy LiquidityMap (confluence adapter)
```

Single structural truth: **`StructureSnapshot`**. This engine does not rediscover
swings, BOS, or CHoCH.

---

## Public API

```python
from services.quant_engine.liquidity import (
    analyze_liquidity,
    LiquidityEngine,
    LIQUIDITY_ENGINE_VERSION,
)

snapshot = analyze_liquidity(
    candles,
    snapshot=structure_snapshot,
    atr=features.atr,
    as_of_index=len(candles) - 1,
)

engine = LiquidityEngine()
out = engine.run(patterns, candles, features)  # scoring adapter
snap = engine.analyze(candles, patterns=patterns, features=features)
```

---

## Pool types

| Type | Source |
|------|--------|
| `EQUAL_HIGH` / `EQUAL_LOW` | Structure EQUAL_* relations + ATR clustering of external highs/lows |
| `STRUCTURAL_HIGH` / `STRUCTURAL_LOW` | Confirmed HH/LH/HL/LL relations from `StructureSnapshot` |
| `SESSION_HIGH` / `SESSION_LOW` | Completed Asia / London / New York UTC windows |

Each pool carries:

- `price`, `side`, `scope`, `status`, `strength`
- `created_index` / `available_index`
- `created_at` / `available_at`
- `source_timeframe` (MTF-safe)
- `source_reference`, explainable `reasons`

### Equality tolerance

```text
tol = max(min_tick, atr_fraction * ATR)
default atr_fraction = 0.15, min_tick = 1e-5
```

Configurable via `ClusterConfig`.

### Session windows (UTC)

| Session | Hours (UTC) |
|---------|-------------|
| Asia | 00:00–08:00 |
| London | 08:00–16:00 |
| New York | 13:00–21:00 |

Session pools are emitted only for **completed** sessions.
`available_at = session_end` (UTC).

---

## Lifecycle

| Status | Meaning |
|--------|---------|
| `ACTIVE` | Known and not yet taken out |
| `SWEPT` | Swept with rejection (close back) |
| `INVALIDATED` | Clean breakout acceptance beyond the level |
| `EXPIRED` | Older than `expire_bars` (default 500) without interaction |

---

## Sweeps vs breakouts

Against an **already available** pool (`available_index < bar_index`):

### Sweep high

1. `high > pool.price`
2. `close < pool.price` (rejection)

→ `SWEEP_HIGH`

### Sweep low

1. `low < pool.price`
2. `close > pool.price`

→ `SWEEP_LOW`

### Breakout (not a sweep)

Close accepted beyond the level (no rejection) → `BREAKOUT` and pool
`INVALIDATED`.

---

## Sweep grade (WEAK / MODERATE / STRONG)

Measurable score from:

- structural pool (+2)
- touches ≥2/3 (+1/+2)
- penetration in ATR bands (+1/+2)
- rejection % ≥50/70 (+1/+2)

Bias alignment (`CONTINUATION` / `STOP_HUNT` / `NEUTRAL`) is separate and kept
for confluence compatibility.

---

## Causality

- Pools with `available_index > as_of_index` are excluded.
- Sweeps only evaluate pools with `available_index < bar_index`.
- Session pools require completed UTC windows.
- Prefix re-runs must not reveal future pools (see acceptance scenario E).

---

## Multi-timeframe

Pools always retain `source_timeframe`. H4 liquidity can be attached to an H1
scan by passing H4-derived pools/snapshot from the caller — the engine never
relabels the source TF.

---

## LiquiditySnapshot

```text
active_pools / swept_pools / recent_sweeps / breakouts
high_liquidity_count / low_liquidity_count
nearest_high_liquidity(price) / nearest_low_liquidity(price)
algorithm_version
legacy_map  → LiquidityMap for existing confluence
```

---

## Persistence

`database/migrations/003_liquidity.sql`:

- `liquidity_pools`
- `liquidity_sweeps`

Both store `algorithm_version`.

---

## Tests

```bash
.venv/bin/python -m pytest -q \
  tests/quant_engine/test_liquidity_engine_v1.py \
  tests/quant_engine/test_liquidity_structure_depth.py
```

Acceptance scenarios: equal high/low sweep, session high, breakout≠sweep,
no-lookahead.

---

## Limitations

- Session model is fixed UTC hour bands (not exchange DST calendars).
- Clustering is greedy, not optimal partitioning.
- Engine scoring adapter still emits BUY/SELL points for Decision aggregation;
  that is **not** a trade signal.
- Persistence tables are defined; live scan does not auto-write yet.

---

## Out of scope

Order Blocks, FVG, inducement, kill zones, SMT, execution, AI.

# Market Structure Engine

Causal structure analysis on top of **confirmed swings** from Swing Engine
**v2.3.0** (`SCAN_SWING_VERSION`).

Package: `services/quant_engine/market_structure/`

This engine does **not** rediscover pivots and does **not** instantiate
`SwingEngine`. It never uses candles after `as_of_index`.

---

## Architecture

```text
OHLC
  ↓
Swing Engine v2.3.0 → confirmed swings only
  ↓
analyze_structure / analyze_market_structure
  ↓
HH / HL / LH / LL (+ EQUAL_*)
  ↓
StructureSnapshot (canonical state)
  ↓
BOS / CHOCH events
  ↓
StructureRegime (internal) → MarketTrendLabel (product)
  ↓
MarketStructureStateView (downstream read model)
```

Future layers (Liquidity, FVG, Decision) consume this engine — they are **not**
implemented here.

---

## Public API

```python
from services.quant_engine.market_structure import (
    analyze_structure,           # canonical detector → StructureSnapshot
    analyze_market_structure,    # snapshot + trend + state + classifications
    explain_swing_classifications,
    classify_market_trend,
    MarketTrendLabel,
    build_market_structure_state_view,
)

# Confirmed swings from the live boundary (never result.swings):
from services.quant_engine.swings.boundary import (
    SCAN_SWING_VERSION,          # "2.3.0"
    obtain_confirmed_swings,
    build_scan_structure,
)

swings = obtain_confirmed_swings(candles, version=SCAN_SWING_VERSION)
analysis = analyze_market_structure(candles, swings, symbol="EURUSD")
print(analysis.trend)                 # BULLISH | BEARISH | RANGING | UNDEFINED
print(analysis.state.to_dict())       # structure-state view
print(analysis.bos_events)
```

Low-level contract details: [`market_structure_engine_v1.md`](market_structure_engine_v1.md).

---

## Swing classification (HH / HL / LH / LL)

Comparisons are **same direction** and **same scope track** only:

| Current | Compared to | Result |
|---------|-------------|--------|
| High | previous confirmed High (same scope) | `HH` / `LH` / `EQUAL_HIGH` |
| Low | previous confirmed Low (same scope) | `HL` / `LL` / `EQUAL_LOW` |

Alternating high↔low pairs are **not** compared for relation labels.

Equality uses `StructureDetectorConfig.price_equality_tolerance`.

Explainable records (`explain_swing_classifications`) include:

- current swing id / price / timestamp index  
- previous comparable swing id / price  
- price difference  
- classification  
- symbol / timeframe / swing_engine_version  

EXTERNAL and INTERNAL tracks are independent.

---

## Market trend / regime

### Internal regime (`StructureRegime`)

Richer labels used by confluence / studio:

- `trending_bullish`, `trending_bearish`
- `reversal_pending`, `ranging`, `transitional`

### Product trend (`MarketTrendLabel`)

Stable external vocabulary:

| Label | Meaning |
|-------|---------|
| `BULLISH` | Committed bullish external structure |
| `BEARISH` | Committed bearish external structure |
| `RANGING` | No committed side, but enough structure history to call a range |
| `UNDEFINED` | Insufficient or ambiguous evidence (empty history, pending CHOCH, transitional) |

Mapping is in `trend_labels.py`. Pending CHOCH does **not** force the opposite side.

Illustrative sequences (not the only paths):

```text
HH + HL with bullish external bias     → BULLISH
LH + LL with bearish external bias     → BEARISH
mixed relations, no bias               → RANGING or UNDEFINED
CHOCH pending                          → UNDEFINED
```

---

## BOS (Break of Structure)

**Definition (v1):** a **close** strictly beyond an active structural level that
was already available on a **prior** candle (`break_index > level_available_index`).

- Bullish BOS: close > active high level  
- Bearish BOS: close < active low level  
- Wick-only crossings do **not** count  
- Each level breaks at most once  

**State machine (external track):**

1. Neutral → first valid break → **BOS** (sets bias)  
2. Same-direction break while biased → continuation **BOS**  
3. Opposite break while biased → **CHOCH** (pending opposite; bias unchanged)  
4. While pending: pending-direction break → confirming **BOS**; same-as-prior → cancel pending + continuation **BOS**  

Internal track mirrors the machine but never mutates external bias.

Event payload includes: symbol/timeframe (via caller), timestamp, direction,
broken swing id, broken price, confirming candle index/close, prior/resulting/
pending bias, swing-engine version (on the analysis bundle), detection indices.

---

## CHoCH (Change of Character)

**Definition (v1):** an opposite-direction structural break **while biased**.
It signals a **potential** regime change.

| | BOS | CHoCH |
|--|-----|-------|
| Role | Continues or establishes structure | Challenges structure |
| Bias | May set / confirm bias | Sets **pending** opposite bias only |
| Confirmation | Immediate for continuation / first break | Requires a later confirming BOS |

CHoCH is **not** emitted for every BOS. First break from neutral is BOS, not CHoCH.

Enum spelling in code: `StructureEventType.CHOCH` (product docs may write CHoCH).

---

## Structure state

Canonical causal state: **`StructureSnapshot`**.

Product read model: **`MarketStructureStateView`** via
`build_market_structure_state_view` / `analyze_market_structure`:

- trend, regime, biases  
- last swing high/low  
- last high/low classification  
- last BOS / last CHOCH  
- structure timestamp, as_of_index  
- swing_engine_version  
- explainable classifications  

Legacy adapter `build_market_structure_state` remains for older feature paths.

---

## No-lookahead

For any candle index `T`:

1. Only swings with `confirmation_index <= T` may be supplied.  
2. `analyze_structure(..., as_of_index=T)` must not read candles after `T`.  
3. Extending the series with future candles and re-running at the same `T`
   must reproduce the same events (`tests/quant_engine/test_market_structure_*`).

Offline quality scoring (`score_structure_event`) is separate and defaults to
`allow_lookahead=False` on the live path.

---

## Persistence

Optional table `market_structure_events`  
(`database/migrations/002_market_structure_events.sql`, also in `schema.sql`).

Stores emitted BOS/CHOCH rows with `swing_engine_version`. Analysis itself
remains in-memory each scan; persistence is for replay/audit.

---

## Compatibility

| Component | Version |
|-----------|---------|
| Swing Engine (live) | **2.3.0** |
| Market Structure Engine | **v1** (detector contract frozen) |
| Hierarchy projection | Supports v2.2+ / v2.3 dual-phase facts |

---

## Limitations

- Does not invent missing OHLC or swings.  
- Equal highs/lows are labeled, not “broken” by equality alone.  
- Wick breaks ignored by design.  
- Product `UNDEFINED` is intentionally conservative under pending CHOCH.  
- No Order Blocks / FVG / liquidity / kill zones in this engine.

---

## Tests

```bash
.venv/bin/python -m pytest -q \
  tests/quant_engine/test_market_structure_detector_v1.py \
  tests/quant_engine/test_market_structure_integration.py \
  tests/quant_engine/test_market_structure_acceptance.py
```

Synthetic scenarios: `tests/quant_engine/structure_scenarios.py`
(bullish, bearish, reversal CHOCH, ranging, equal highs).

# FVG / Order Block Zone Lifecycle v1

**Pipeline:** `ANALYSIS_PIPELINE_VERSION = 1.4.0`  
**Algorithms:** `FVG_ZONE_ALGORITHM_VERSION = 1.0.0`, `OB_ZONE_ALGORITHM_VERSION = 1.0.0`

Canonical detectors live in:

- `services/quant_engine/fvg/lifecycle.py` → `detect_fvg_zones` → `FVGZoneSet`
- `services/quant_engine/order_blocks/lifecycle.py` → `detect_order_block_zones` → `OrderBlockZoneSet`

SMC and DecisionEngine consume **ranked pattern views** of those sets. There is exactly one FVG detector and one OB detector.

---

## Audit (pre-1.2.0)

| Item | Finding |
|------|---------|
| Detector | `SMCEngine._detect_fvg` / `_detect_order_blocks` |
| Last-N | **N = 3** — after scanning the full prefix, only `patterns[-3:]` were emitted |
| Why | Soft cap for DecisionEngine pattern volume |
| Candles examined | Full window for formation; emit truncated to newest three |
| Causal formation | Yes (3-candle FVG / impulse OB on prefix) |
| Old zones | Disappeared from the pattern list once newer ones pushed them out |
| Mutable | Patterns were recreate-each-scan (no stable zone id / status) |
| Mitigation | Ad-hoc in feature/scoring helpers, not lifecycle state |
| Invalidation | Not modeled as zone status |
| Coexistence | Only the newest three of each type reached scoring |

---

## Architecture

```text
CANDLES (prefix ≤ T)
   ├─ detect_fvg_zones        → FVGZoneSet (all zones + lifecycle)
   ├─ detect_order_block_zones → OrderBlockZoneSet
   └─ LiquidityEngine          → LiquiditySnapshot
            │
            ▼
   SMCEngine.detect_all
     • BOS/CHOCH from structure
     • patterns_from_fvg_zones (ranked, capped for DE only)
     • patterns_from_ob_zones  (ranked, capped for DE only)
     • patterns_from_liquidity_snapshot
            │
            ▼
   FeatureExtractor / FVG·OB engines / SMC Confluence / DecisionEngine
```

Ranking **never deletes** zones from the canonical sets. Soft pattern limit for DE = 8 (see `patterns.py`).

---

## FVG — what creates a zone?

Three consecutive candles `c1, c2, c3` at indices `i-2, i-1, i` (zone available at `i`):

| Direction | Rule | Bounds |
|-----------|------|--------|
| Bullish (`BUY`) | `c1.high < c3.low` | `[c1.high, c3.low]` |
| Bearish (`SELL`) | `c1.low > c3.high` | `[c3.high, c1.low]` |

Stable id: `fvg-{direction}-{created_index}-{lo}-{hi}`.

### When is it ACTIVE?

At creation: `ACTIVE`, `fill_ratio = 0`, no touch/mitigation indices.

### What counts as a touch / partial fill?

Any later bar (`j > created_index`) whose range intersects `[lower, upper]`:

- Sets `first_touch_index` on first intersection
- Status → `PARTIALLY_FILLED`
- **Fill rule (wick penetration):**
  - Bullish: depth from upper bound downward via `low`; `fill_ratio = depth / gap`
  - Bearish: depth from lower bound upward via `high`

### What is full mitigation?

| Direction | Rule |
|-----------|------|
| Bullish | Later `low <= lower_bound` → `fill_ratio = 1`, `MITIGATED` |
| Bearish | Later `high >= upper_bound` → `fill_ratio = 1`, `MITIGATED` |

### Invalidation / expiration?

No separate `INVALIDATED` / `EXPIRED` states in v1. Full mitigation is the terminal fill state. Zones **remain in the set** after mitigation (status `MITIGATED`). No arbitrary age-based deletion.

### Multiple zones

All zones created on the prefix are retained. Newer zones do not evict older valid ones.

---

## Order Block — what creates a zone?

For source index `i` with confirmation at `i+1` (zone available at `created_index = i+1`):

| Direction | Rule | Zone |
|-----------|------|------|
| Bullish | Down candle at `i`, up at `i+1`, `body(i+1) > 1.5 * body(i)` | `[low_i, high_i]` |
| Bearish | Up at `i`, down at `i+1`, same impulse | `[low_i, high_i]` |

### States

| Status | Meaning |
|--------|---------|
| `ACTIVE` | Created; no later range intersection |
| `TOUCHED` | Later bar range intersects OB |
| `MITIGATED` | Close through opposite side |

### Mitigation (canonical)

| Direction | Rule |
|-----------|------|
| Bullish | Later `close < price_low` |
| Bearish | Later `close > price_high` |

Touch uses range intersection (wick allowed). Mitigation uses **close** through the far side (explicit wick/close split).

No expiration. Mitigated OBs remain in the set.

---

## Ranking (for DE patterns only)

See [ZONE_RANKING.md](ZONE_RANKING.md) (pipeline **1.3.0**).

Lexicographic order after context enrichment:

1. lifecycle validity  
2. structure alignment  
3. liquidity relation  
4. trend alignment  
5. ATR-normalized distance (0 if price inside zone)  
6. freshness bars  
7. stable `zone_id`

Soft cap **8** applies only after ranking. Zone sets remain complete.

---

## Causality / no lookahead

`detect_*(candles, as_of_index=T)` and `detect_*(candles[:T+1])` are equivalent. Mitigation at `T+k` cannot appear in the snapshot at `T`.

Live / replay / backtest share `analyze_candle_window`, which builds zone sets once and passes them into SMC.

---

## Related

- [CURRENT_ARCHITECTURE.md](CURRENT_ARCHITECTURE.md)
- [ANALYTICAL_PARITY.md](ANALYTICAL_PARITY.md)
- [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md)
- Supersedes the “last-N only” limitation in [FVG_OB_LIMITATIONS.md](FVG_OB_LIMITATIONS.md)

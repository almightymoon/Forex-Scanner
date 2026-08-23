# Single confirmed-swing pass — architecture inventory

**Status:** live on `main` (Market Structure v1 + unified scan path).  
**Live swing version:** `SCAN_SWING_VERSION = FEATURE_SWING_VERSION = "2.3.0"`  
(explicit cutover; not a silent substitution).

This document is the Phase 1 inventory for making confirmed swings the **single
source of truth** for structure during one scan.

---

## Before (duplicate structure discovery)

```text
candles
   ├── FeatureExtractor → obtain swings (FEATURE version) → analyze_structure
   ├── SMC → build_zigzag_swings / analyze_market_structure → BOS/CHoCH
   └── MarketStructureEngine.run → find_swings / classify_bos (fallback)
```

Problems:

* Multiple SwingEngine / zigzag invocations per scan
* Version ambiguity (feature path vs zigzag default)
* SMC BOS/CHoCH could disagree with FeatureExtractor structure
* Silent rediscovery when `features` / snapshot omitted

---

## After (canonical single pass)

```text
candles
   ↓
build_scan_structure(version=SCAN_SWING_VERSION)   ← ONE SwingEngine.detect
   ↓
ScanStructureInput
   · confirmed_swings
   · swing_version
   · StructureSnapshot
   ↓
├── DataLoader → SMCEngine.detect_all(swings, snapshot)   # BOS/CHoCH from snapshot
├── SignalBuilder → DecisionEngine.evaluate(..., structure_input=)
│       ├── FeatureExtractor.extract(swings, snapshot)
│       ├── TrendEngine.analyze(..., features)
│       └── MarketStructureEngine.run_from_structure_snapshot(snapshot, ...)
└── (MTF HTF series: separate candle series → own obtain; not LTF duplicate)
```

Invariant:

> The LTF scan computes confirmed swings **once**. Downstream structure
> consumers receive those swings / that snapshot; they do not rediscover pivots.

---

## Trace — one complete scan

| Stage | Where | Swings | Version | Structure |
|-------|--------|--------|---------|-----------|
| Producer | `DataLoader.load` → `build_scan_structure` | `obtain_confirmed_swings` once | `SCAN_SWING_VERSION` (2.3.0) | `analyze_structure` once |
| SMC | `SMCEngine.detect_all` | injected | n/a | injected snapshot → BOS/CHoCH |
| Decision | `DecisionEngine.evaluate` | from ctx / `ScanStructureInput` | explicit | reuse snapshot |
| Features | `FeatureExtractor.extract` | injected | `FEATURE_SWING_VERSION` only if missing | reuse snapshot if `as_of` matches |
| Trend | `TrendEngine.analyze` | via `features` | n/a | snapshot fields on features |
| Scoring | `MarketStructureEngine.run_from_structure_snapshot` | n/a | n/a | snapshot required |

### Canonical producer location

`services/quant_engine/swings/boundary.py`

* `obtain_confirmed_swings` — SwingEngine once, `confirmed_swings` only
* `build_scan_structure` — swings + `StructureSnapshot` → `ScanStructureInput`

### Duplicate work removed (live LTF path)

Previously: FeatureExtractor + SMC + MarketStructureEngine fallback each could
run independent swing/structure discovery (**up to 3**).

Now on live path: **1** confirmed-swing pass + **1** `analyze_structure`.

Remaining `SwingEngine(` / zigzag call sites under
`services/quant_engine` + `services/scanner_service`:

| Site | Classification |
|------|----------------|
| `swings/boundary.py` `obtain_confirmed_swings` | **Canonical producer** |
| `swing_analysis.py` `build_zigzag_swings` / `find_swings` / `analyze_market_structure` | **Legacy compatibility** (deprecated; not used by live scan) |
| `market_structure/mtf_bias.py` | **Per-TF series** (HTF candles, not LTF duplicate) |
| Comments / docs mentioning zigzag | Documentation only |

---

## Version boundary

```text
CURRENT_LIVE_SWING_VERSION = "2.3.0"
EXPLICIT_V2_3_AVAILABLE = true
CUTOVER_RECOMMENDED = false   # already cut over deliberately (PR #3 lineage)
```

Callers may still request `version="2.0.0"` explicitly via
`obtain_confirmed_swings(..., version="2.0.0")`. The live default is **not**
silently reverted.

---

## Causal detection vs offline scoring

See `docs/market_structure_engine_v1.md`:

* **CAUSAL STRUCTURE DETECTION** — `analyze_structure` (no lookahead)
* **OFFLINE STRUCTURE QUALITY SCORING** — `score_structure_event(..., allow_lookahead=True)` for diagnostics only; live default `allow_lookahead=False`

# SMC Confluence Engine v1

Thin orchestration layer that assembles **already-computed** Structure,
Liquidity, FVG, Order Block, and MTF artifacts into one explainable
`SMCContextSnapshot` for the Decision Engine.

**Version:** `1.0.0` (`SMC_CONFLUENCE_ENGINE_VERSION`)

This engine does **not**:

- detect swings, BOS/CHOCH, liquidity pools, FVGs, or order blocks
- produce BUY/SELL trade decisions
- replace the Decision Engine’s 100-point score

---

## Architecture

```text
Swing Engine (v2.3.0)
      ↓
Market Structure Engine → StructureSnapshot
      ↓
Liquidity Engine v1     → LiquiditySnapshot
FVG Engine              → EngineOutput + patterns
Order Block Engine      → EngineOutput + patterns
MTF map                 → TrendDirection per TF
      ↓
SMC Confluence Engine v1 → SMCContextSnapshot
      ↓
Decision Engine          → final score / direction / gating
```

Package: `services/quant_engine/smc_confluence/`

| File | Role |
|------|------|
| `models.py` | `SMCContextSnapshot`, bias/strength enums, evidence/conflict items |
| `engine.py` | `build_smc_context()` / `SMCConfluenceEngine` |

Existing setup scoring (`assess_setup_confluence`) is **wrapped**, not replaced.
Its result is embedded as `setup_confluence` on the snapshot.

---

## Inputs

All optional except `symbol` + `timeframe`. Prefer precomputed snapshots:

| Input | Source |
|-------|--------|
| `structure_snapshot` | Market Structure Engine / FeatureExtractor |
| `liquidity_snapshot` | Liquidity Engine / FeatureExtractor |
| `patterns` | SMC detectors (OB / FVG / BOS patterns already found) |
| `mtf_trends` | Caller MTF map (`D1`/`H4`/`H1`/`M15`/…) |
| `fvg_output` / `order_block_output` | DecisionEngine engine runs |
| `features` | Shared `MarketFeatures` (fallback fields) |

**No detector is re-run inside this package.**

`LiquidityEngine.run` reuses `features.liquidity_snapshot` when present so
DecisionEngine does not call `analyze_liquidity` twice.

---

## Output contract — `SMCContextSnapshot`

| Field | Meaning |
|-------|---------|
| `symbol`, `timeframe`, `as_of_index`, `timestamp` | Causal identity |
| `trend` | Product `MarketTrendLabel` |
| `structure_regime`, `external_bias`, `pending_external_bias` | Structure |
| `last_bos`, `last_choch` | Latest structure events (dicts) |
| `liquidity_context` | Active highs/lows + recent sweeps |
| `fvg_context`, `order_block_context` | Counts + engine scores |
| `mtf_context` | HTF/LTF trend maps |
| `bullish_confluences` / `bearish_confluences` | Weighted `EvidenceItem`s |
| `conflicts` | Explicit conflict records |
| `bullish_score` / `bearish_score` | Sum of evidence weights |
| `evidence_strength` | Normalized 0..1 (not the DE final score) |
| `dominant_bias` | `BULLISH` / `BEARISH` / `MIXED` / `NEUTRAL` / `UNDEFINED` |
| `confluence_strength` | `NONE` / `WEAK` / `MODERATE` / `STRONG` |
| `confidence` | Context confidence (separate from DE confidence) |
| `explanations` | Deterministic strings from evidence |
| `setup_confluence` | Embedded `SetupConfluenceAssessment` |
| `algorithm_versions` | Confluence + component versions |

---

## Confluence logic

Evidence is additive by category with timeframe weights:

| TF | Weight |
|----|--------|
| D1 | 3.0 |
| H4 | 2.5 |
| H1 | 2.0 |
| M30 | 1.5 |
| M15 | 1.2 |
| M5 | 1.0 |

### Structure

- Committed external bias (±2 × TF weight)
- Product trend BULLISH/BEARISH (+1.5)
- Latest BOS direction (+1.2)
- CHOCH → conflict flag (does not force a side)
- `UNDEFINED` product trend with low total evidence → `UNDEFINED` bias

### Liquidity (terminology)

- **Sell-side** = lows / buy stops → `SWEEP_LOW` contributes **bullish**
- **Buy-side** = highs / sell stops → `SWEEP_HIGH` contributes **bearish**
- Active pools only add weight when aligned with external bias
- `CONTINUATION` / `STOP_HUNT` adjusts sweep weight

### FVG / OB

- Pattern counts by `SignalDirection`
- Conflicting FVG vs OB → conflict item

### MTF

- Each TF trend adds weight on its side
- HTF disagreement and HTF↔LTF fights → conflicts

### Dominant bias

1. Insufficient structure + low evidence → `UNDEFINED`
2. Conflicts with near-tied scores → `MIXED`
3. Clear lead → `BULLISH` / `BEARISH` with strength from magnitude
4. Else → `NEUTRAL`

**This is evidence strength, not a trade recommendation.**

---

## Conflict handling

Conflicts are always listed (never silently averaged away), including:

- Undefined / CHOCH structure
- HTF mixed or HTF vs LTF
- Bullish FVG vs bearish OB (and reverse)
- Both high and low liquidity recently swept

DecisionEngine adds **warnings** for `MIXED` / `UNDEFINED` without changing the
100-point arithmetic (v1 integration boundary).

---

## Causality / no lookahead

`build_smc_context` trusts that callers pass **already causal** snapshots:

- Structure events with `break_index > as_of` must not be in the snapshot
- Liquidity pools/sweeps beyond `as_of_index` must not be in the snapshot

FeatureExtractor + Liquidity/Structure analyzers enforce this upstream.
Acceptance scenario E asserts earlier snapshots omit later BOS/sweeps.

---

## Determinism

Same symbol / TF / inputs / engine versions → identical `to_dict()`.

No randomness, wall-clock time, or unordered set iteration in scoring.

---

## Decision Engine integration

`DecisionEngine.evaluate`:

1. Extracts features (structure + liquidity once)
2. Runs scoring engines (LiquidityEngine reuses snapshot)
3. Resolves direction + structure policy (unchanged)
4. Calls `build_smc_context(...)` with precomputed artifacts
5. Attaches `smc_context` to `market_features` and `explainability`
6. Surfaces MIXED/UNDEFINED as warnings only

Final score remains `sum(engine scores) + structure_policy.score_delta`.

---

## Persistence

No dedicated table in v1. Context is computed per scan and stored inside
`scanner_results` / signal payload via `market_features.smc_context` when the
API persists the signal JSON.

---

## Tests

`tests/quant_engine/test_smc_confluence_engine.py`

- Scenarios A–E (strong bull/bear, mixed, undefined, future-event)
- Determinism
- Structure + liquidity pairing
- DecisionEngine attachment regression

---

## Related docs

- `docs/MARKET_STRUCTURE_ENGINE.md`
- `docs/LIQUIDITY_ENGINE.md`
- `docs/MARKET_DATA_SWING_PIPELINE.md`

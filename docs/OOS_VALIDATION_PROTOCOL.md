# OOS Validation Protocol

**Purpose:** Honest out-of-sample evaluation of the **frozen** analytical pipeline.  
**Frozen version:** `ANALYSIS_PIPELINE_VERSION = 1.4.0` (see [ANALYTICAL_FREEZE.md](ANALYTICAL_FREEZE.md))

This protocol does **not** optimize parameters. It locks analysis, applies realistic execution, and measures results.

---

## DATA

| Field | Contract |
|-------|----------|
| Symbol | Declared per locked dataset (default target: **XAUUSD**) |
| Timeframe | Declared per locked dataset (default target: **H1**) |
| Date range | Declared in [OOS_DATASET_CONTRACT.md](OOS_DATASET_CONTRACT.md) |
| Timezone | **UTC** candle timestamps |
| Candle source | Dataset-declared (MT5 export / collector / fixture) — single source |
| Missing data | No silent fill of gaps for scoring; document gaps; skip incomplete prefixes |

Dataset must be **locked and versioned** before the run. Do not replace candles after seeing results.

---

## ANALYSIS

| Field | Rule |
|-------|------|
| Pipeline | `analyze_candle_window` only |
| Version | Frozen `ANALYSIS_PIPELINE_VERSION` |
| Ranking | Frozen lexicographic order; HTF via `select_ranking_htf_trend` |
| DecisionEngine weights | Frozen config — no retune |
| HTF | Causal `resolve_mtf_trends` / `merge_htf_bars` (provider preferred, rollup fill) |
| Drift | Observational only (`compare_htf_context`) — does not alter signals |

---

## EXECUTION

| Field | Rule |
|-------|------|
| Entry | Signal on closed LTF bar; enter at next-bar open (or dataset-declared rule) |
| Spread | Fixed dataset-declared spread (price units) |
| Slippage | Fixed dataset-declared slippage |
| Commission | Fixed dataset-declared commission |
| SL / TP | From `ScannerSignal` at signal time — no post-hoc move |
| Ambiguous candle | If same bar hits SL and TP, use repository ambiguous-fill rule (document result) |

Execution is **outside** analytical fingerprint equality.

---

## VALIDATION

| Rule | Definition |
|------|------------|
| Chronological split | Train/calibration window **ends before** test window starts |
| Walk-forward | Optional rolling folds; each fold freezes params before its test segment |
| No test tuning | Parameters may not be chosen using test outcomes |
| No lookahead | HTF incomplete bars excluded; prefixes causal |

---

## METRICS (required)

Record for the locked test segment:

- total trades
- win rate
- profit factor
- expectancy
- average R
- total R
- max drawdown
- average winner
- average loser
- consecutive losses

Optional: equity curve dump, per-trade journal.

---

## FORBIDDEN

- Threshold / ranking / weight optimization on test
- Favorable date-range shopping
- Removing losing trades
- Quietly replacing the dataset after poor results

If data quality is bad: **version a new dataset** and document why — do not mutate the locked one.

---

## NEXT TASK

1. Lock dataset per [OOS_DATASET_CONTRACT.md](OOS_DATASET_CONTRACT.md)  
2. Run frozen pipeline  
3. Apply realistic execution  
4. Walk-forward / OOS  
5. Measure metrics above  

No analytical feature work unless a correctness defect is found.

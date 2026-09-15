# Experiment Report — Pipeline 1.6.0 (Arm H3)

**Status:** FAILED EXPERIMENT  
**Generated:** 2026-09-15T15:06:48.635988+00:00

## Predeclared design

| Field | Value |
|-------|-------|
| Arm | H3 — direction / structure / HTF emit gating |
| Baseline analysis | `1.4.0` (unchanged) |
| Experiment version | `1.6.0` (emit gate only) |
| Dataset | `xauusd_h1_oos_v1_retrospective_2022_2024` |
| Hash | `eac96d050a6bacfe879a0506143a053d4ce5ab7304b94cfbab91067211040d73` |
| Fit | TRAIN 2022 / VALIDATION 2023 (enriched from 1.5.0 corpora) |
| TEST | 2024-01-01 → 2024-07-11 (once) |

### Selection criteria (VALIDATION)

- expectancy ≥ 0.0
- profit factor ≥ 1.0
- trades ≥ 20

### TEST success criteria

- positive expectancy
- profit factor ≥ 1.0
- total R ≥ baseline (-22.434) − 5.0

## Selection (locked before TEST)

| Field | Value |
|-------|-------|
| Qualified | False |
| Selected | `h3_sell_only` |
| Reason | no_policy_met_gates_diagnostic_best |

**Important:** On TRAIN, buy-side and structure-aligned gates looked positive (e.g. `h3_buy_only` exp=+0.061). On VALIDATION **every** candidate was negative; the least-bad diagnostic was ironically `h3_sell_only` (exp=−0.017) — the opposite of the OOS forensics narrative that shorts dominate losses on 2024 TEST. That mismatch is why VAL gating exists.

VALIDATION ranking (all failed promotion):

| Policy | n | exp | PF | qualified |
|--------|---|-----|-----|-----------|
| h3_sell_only | 204 | −0.017 | 0.93 | False |
| h3_dual_aligned | 297 | −0.041 | 0.948 | False |
| h3_structure_aligned_only | 312 | −0.049 | 0.941 | False |
| h3_block_htf_opposed | 433 | −0.058 | 0.888 | False |
| h3_htf_aligned_only | 433 | −0.058 | 0.888 | False |
| h3_block_structure_opposed | 443 | −0.071 | 0.877 | False |
| h3_baseline_all | 473 | −0.081 | 0.858 | False |
| h3_buy_structure_aligned | 194 | −0.083 | 0.903 | False |
| h3_buy_dual_aligned | 184 | −0.084 | 0.894 | False |
| h3_buy_block_structure_opposed | 255 | −0.123 | 0.824 | False |
| h3_buy_only | 269 | −0.129 | 0.813 | False |

## TEST results (observed once)

| Metric | 1.6.0 H3 | 1.4.0 BASE |
|--------|----------|------------|
| Trades | 101 | 246 |
| Win rate | 34.7 | 38.6 |
| Profit factor | 0.674 | 0.761 |
| Expectancy | -0.182 | -0.091 |
| Total R | -18.355 | -22.434 |

Success checks:

```json
{
  "passed": false,
  "checks": {
    "positive_expectancy": false,
    "profit_factor": false,
    "total_r_not_worse_than_baseline_tolerance": true
  },
  "criteria": {
    "require_positive_expectancy": true,
    "require_pf_at_least": 1.0,
    "max_total_r_worse_than_baseline": 5.0
  },
  "baseline_total_r": -22.434,
  "total_r_floor": -27.434,
  "observed": {
    "expectancy": -0.182,
    "profit_factor": 0.674,
    "total_r": -18.355,
    "total_trades": 101,
    "win_rate": 34.7
  }
}
```

## OBSERVED / INFERRED / UNKNOWN

**OBSERVED:** Emit-filtered TEST metrics above; selection used VALIDATION only; 1.4.0 analytical
code paths untouched.

**INFERRED:** H3 direction/alignment gating did not recover a validated edge under predeclared criteria.

**UNKNOWN:** Live fills, prospective generalization, whether exit geometry (H2) would fare better.

## Non-claims

- Does not amend or rehabilitate frozen 1.4.0.
- Does not authorize combining with failed H1 score bands into a silent dump.
- Subgroup forensics remain exploratory; this arm tested only the predeclared candidate set.

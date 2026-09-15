# Experiment Report — Pipeline 1.7.0 (Arm H2)

**Status:** FAILED EXPERIMENT  
**Generated:** 2026-09-15T15:28:23.455325+00:00

## Predeclared design

| Field | Value |
|-------|-------|
| Arm | H2 — exit / payoff geometry (TP remap) |
| Baseline analysis | `1.4.0` (unchanged) |
| Experiment version | `1.7.0` |
| Mechanism | Keep original SL; set TP = entry ± target_rr × risk (or baseline TP) |
| Dataset hash | `eac96d050a6bacfe879a0506143a053d4ce5ab7304b94cfbab91067211040d73` |
| Fit | TRAIN 2022 / VALIDATION 2023 |
| TEST | 2024-01-01 → 2024-07-11 (once) |
| Execution | signal_close / sl_first / costs 0 |

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
| Selected | `h2_tp_rr_2_5` |
| Reason | no_policy_met_gates_diagnostic_best |

VALIDATION ranking:

| Policy | n | exp | PF | total R | qualified |
|--------|---|-----|-----|---------|-----------|
| h2_tp_rr_2_5 | 473 | -0.028 | 0.949 | -13.0506 | False |
| h2_tp_rr_3_0 | 473 | -0.034 | 0.92 | -16.0574 | False |
| h2_tp_rr_2_0 | 473 | -0.047 | 0.92 | -22.4226 | False |
| h2_baseline_rr_133 | 473 | -0.081 | 0.858 | -38.1977 | False |
| h2_tp_rr_1_5 | 473 | -0.082 | 0.864 | -38.6147 | False |
| h2_tp_rr_1_0 | 473 | -0.094 | 0.814 | -44.5157 | False |
| h2_tp_rr_0_75 | 473 | -0.134 | 0.711 | -63.172 | False |

## TEST results (observed once)

| Metric | 1.7.0 H2 | 1.4.0 BASE report |
|--------|----------|-------------------|
| Trades | 246 | 246 |
| Win rate | 28.5 | 38.6 |
| Profit factor | 0.764 | 0.761 |
| Expectancy | -0.143 | -0.091 |
| Total R | -35.2323 | -22.434 |

Success checks:

```json
{
  "passed": false,
  "checks": {
    "positive_expectancy": false,
    "profit_factor": false,
    "total_r_not_worse_than_baseline_tolerance": false
  },
  "criteria": {
    "require_positive_expectancy": true,
    "require_pf_at_least": 1.0,
    "max_total_r_worse_than_baseline": 5.0
  },
  "baseline_total_r": -22.434,
  "total_r_floor": -27.434,
  "observed": {
    "expectancy": -0.143,
    "profit_factor": 0.764,
    "total_r": -35.2323,
    "total_trades": 246,
    "win_rate": 28.5
  }
}
```

## OBSERVED / INFERRED / UNKNOWN

**OBSERVED:** TP-geometry filtered TEST metrics above; selection used VALIDATION only; 1.4.0
signal generation untouched.

**INFERRED:** H2 TP remapping did not recover a validated edge under predeclared criteria.

**UNKNOWN:** Live fills, partial exits / trailing stops, multi-target scaling, prospective data.

## Non-claims

- Does not amend frozen 1.4.0 analysis or DecisionEngine weights.
- Does not combine with failed H1/H3 gates.
- Changing RR alone cannot invent directional edge if hit-rate remains below breakeven for that RR.

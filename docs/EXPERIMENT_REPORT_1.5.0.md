# Experiment Report — Pipeline 1.5.0 (Arm H1)

**Status:** FAILED EXPERIMENT  
**Generated:** 2026-09-15T14:24:59.978748+00:00

## Predeclared design

| Field | Value |
|-------|-------|
| Arm | H1 — score/confidence emit calibration |
| Baseline analysis | `1.4.0` (unchanged) |
| Experiment version | `1.5.0` (emit gate only) |
| Dataset | `xauusd_h1_oos_v1_retrospective_2022_2024` |
| Hash | `eac96d050a6bacfe879a0506143a053d4ce5ab7304b94cfbab91067211040d73` |
| Fit | TRAIN 2022 / VALIDATION 2023 |
| TEST | 2024-01-01 → 2024-07-11 (once) |
| Cadence | lookback=250, stride=4, min_score=70 |

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
| Selected | `h1_baseline_min70` |
| Reason | no_policy_met_gates_diagnostic_best |

**Important:** Several score/confidence bands looked **positive on TRAIN** (e.g. `h1_score_band_71_84` TRAIN exp=+0.208, PF=1.531) but **all candidates were negative on VALIDATION**. That is exactly why selection is VAL-gated — the OOS forensics “low score looks better” pattern did not replicate on 2023.

VALIDATION ranking (all failed promotion gates):

| Policy | n | exp | PF |
|--------|---|-----|-----|
| h1_baseline_min70 | 473 | −0.081 | 0.858 |
| h1_score_band_71_94 | 188 | −0.143 | 0.778 |
| h1_score_cap_94 | 193 | −0.165 | 0.751 |
| h1_score_band_71_84 | 56 | −0.235 | 0.607 |
| h1_score_cap_84 | 61 | −0.298 | 0.544 |
| h1_score_cap_84_conf_cap_084 | 46 | −0.323 | 0.478 |
| h1_excl_high_conf | 63 | −0.361 | 0.487 |
| h1_conf_lt_060 | 15 | −0.393 | 0.385 |

VALIDATION metrics for diagnostic-best policy:

```json
{
  "total_trades": 473,
  "wins": 191,
  "losses": 282,
  "breakeven": 0,
  "win_rate": 40.4,
  "profit_factor": 0.858,
  "expectancy": -0.081,
  "avg_r": -0.081,
  "max_drawdown_r": 55.691,
  "max_drawdown_pips": 44717.11,
  "avg_winner_pips": 969.82,
  "avg_loser_pips": -765.19,
  "consecutive_wins_max": 7,
  "consecutive_losses_max": 11,
  "avg_score": 93.8,
  "total_r": -38.1977,
  "gross_profit": 1852.347143,
  "gross_loss": -2157.822143,
  "ambiguous_trades": 21,
  "win_rate_se_approx": 2.26,
  "win_rate_ci95_approx": [
    36.0,
    44.8
  ]
}
```

## TEST results (observed once)

| Metric | 1.5.0 H1 | 1.4.0 BASE |
|--------|----------|------------|
| Trades | 246 | 246 |
| Win rate | 38.6 | 38.6 |
| Profit factor | 0.761 | 0.761 |
| Expectancy | -0.091 | -0.091 |
| Total R | -22.434 | -22.434 |

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
    "expectancy": -0.091,
    "profit_factor": 0.761,
    "total_r": -22.434,
    "total_trades": 246,
    "win_rate": 38.6
  }
}
```

## OBSERVED / INFERRED / UNKNOWN

**OBSERVED:** Emit-filtered TEST metrics above; selection used VALIDATION only; 1.4.0 analytical
code paths untouched.

**INFERRED:** H1 emit calibration did not recover a validated edge under predeclared criteria.

**UNKNOWN:** Live fills, prospective generalization, whether other arms (H2/H3) would fare better.

## Non-claims

- Does not amend or rehabilitate frozen 1.4.0.
- Does not authorize silent score-weight tuning.
- Subgroup forensics remain exploratory; this arm tested only the predeclared candidate set.

# Experiment Report — Pipeline 1.8.0 (Arm H4)

**Status:** PASSED EXPERIMENT SUCCESS CRITERIA  
**Generated:** 2026-09-15T16:21:11.684127+00:00

## Predeclared design

| Field | Value |
|-------|-------|
| Arm | H4 — zone rank / liquidity emit gating |
| Baseline analysis | `1.4.0` unchanged |
| Labels | forensics-compatible `primary_rank`, `liquidity_relation` |
| Dataset hash | `eac96d050a6bacfe879a0506143a053d4ce5ab7304b94cfbab91067211040d73` |

### Selection / TEST criteria

Same floors as H1–H3 (VAL exp≥0, PF≥1, n≥20; TEST exp>0, PF≥1, total R≥−27.434).

## Selection (locked before TEST)

| Field | Value |
|-------|-------|
| Qualified | True |
| Selected | `h4_rank1_liquidity_none` |
| Reason | met_validation_gates |

| Policy | n | exp | PF | total R | qualified |
|--------|---|-----|-----|---------|-----------|
| h4_rank1_liquidity_none | 56 | 0.034 | 1.227 | 1.88 | True |
| h4_rank1_exclude_sweep | 120 | 0.024 | 1.028 | 2.8384 | True |
| h4_rank1_only | 423 | -0.04 | 0.921 | -17.0499 | False |
| h4_rank_le_2 | 447 | -0.062 | 0.889 | -27.5317 | False |
| h4_liquidity_near_or_none | 142 | -0.073 | 0.874 | -10.31 | False |
| h4_baseline_all | 473 | -0.081 | 0.858 | -38.1977 | False |
| h4_exclude_associated_sweep | 144 | -0.085 | 0.848 | -12.31 | False |
| h4_liquidity_none_only | 71 | -0.104 | 0.961 | -7.4047 | False |

## TEST results

| Metric | 1.8.0 H4 | 1.4.0 BASE |
|--------|----------|------------|
| Trades | 18 | 246 |
| Win rate | 44.4 | 38.6 |
| Profit factor | 1.288 | 0.761 |
| Expectancy | 0.037 | -0.091 |
| Total R | 0.6667 | -22.434 |

```json
{
  "passed": true,
  "checks": {
    "positive_expectancy": true,
    "profit_factor": true,
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
    "expectancy": 0.037,
    "profit_factor": 1.288,
    "total_r": 0.6667,
    "total_trades": 18,
    "win_rate": 44.4
  }
}
```

## OBSERVED / INFERRED / UNKNOWN

**OBSERVED:** Selection on VALIDATION only; TEST used locked enrichment cache; 1.4.0 untouched.
Selected `h4_rank1_liquidity_none` met predeclared TEST floors with **n=18** trades
(WR 44.4%, PF 1.288, exp +0.037, total R +0.667).

**INFERRED:** Rank-1 + liquidity NONE is a candidate emit filter worth paper/shadow monitoring;
sample size is too small to claim a robust live edge.

**UNKNOWN:** Prospective post-2026H1 (H5 accrual incomplete); stability under costs; whether
NONE liquidity is durable or a 2024 sample artifact.

## Non-claims

- Does not rehabilitate 1.4.0 or combine with failed H1–H3 arms.

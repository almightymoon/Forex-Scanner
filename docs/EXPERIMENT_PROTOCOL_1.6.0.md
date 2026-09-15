# Experiment Protocol — Pipeline 1.6.0 (Arm H3)

**Status:** COMPLETE — Arm **H3** **FAILED EXPERIMENT** (see `docs/EXPERIMENT_REPORT_1.6.0.md`)  
**Frozen baseline:** 1.4.0 (do not modify)  
**Prior experiment:** 1.5.0 H1 **FAILED** (no VAL-qualified score gate)  
**Experiment version:** `1.6.0` (emit gate only; analysis fingerprints remain 1.4.0)

## Hard rules

1. Never edit 1.4.0 behavior in place.
2. No tuning on locked 2024 TEST — select on VALIDATION only; TEST once.
3. One hypothesis family: **H3 only** (do not combine with H1 bands).
4. Predeclared criteria below (identical floors to H1 for comparability).
5. Execution rules unchanged (`docs/BACKTEST_EXECUTION.md`).

## Dataset

Same locked package as 1.4.0 / 1.5.0:

| Field | Value |
|-------|-------|
| Dataset ID | `xauusd_h1_oos_v1_retrospective_2022_2024` |
| Hash | `eac96d050a6bacfe879a0506143a053d4ce5ab7304b94cfbab91067211040d73` |
| TRAIN / VAL / TEST | 2022 / 2023 / 2024-01-01→2024-07-11 |

Cadence unchanged (lookback 250, stride 4, min_score 70). Fit trades reused from
`validation_1_5_0` and **enriched** with structure/HTF via frozen 1.4.0 re-analysis.

## Arm H3 — implementation contract

| Field | Content |
|-------|---------|
| Hypothesis | Shorts and/or structure/HTF-opposed setups dominate losses; gating them improves expectancy |
| Mechanism | Post-analysis emit gate (`calibration_1_6_0.py`) |
| Alignment labels | Same `align_bias()` as OOS forensics |
| Candidates | See `CANDIDATE_POLICIES` |

### Predeclared VALIDATION selection

- expectancy ≥ 0
- profit factor ≥ 1.0
- trades ≥ 20

### Predeclared TEST success

- expectancy > 0
- profit factor ≥ 1.0
- total R ≥ −22.434 − 5.0 (= −27.434)

## Runner

```bash
python scripts/run_oos_experiment_1_6_0.py --enrich
python scripts/run_oos_experiment_1_6_0.py --select
python scripts/run_oos_experiment_1_6_0.py --test
python scripts/run_oos_experiment_1_6_0.py --finalize
```

Artifacts: `validation_1_6_0/` + `docs/EXPERIMENT_REPORT_1.6.0.md`

# Experiment Protocol — Pipeline 1.5.0

**Status:** COMPLETE — Arm **H1** **FAILED EXPERIMENT** (see `docs/EXPERIMENT_REPORT_1.5.0.md`)  
**Frozen baseline:** 1.4.0 (do not modify)  
**Experiment version:** `1.5.0` (emit gate only; analysis fingerprints remain 1.4.0)

Authorized by product request to continue building after 1.4.0 closure.

## Hard rules

1. **Never edit 1.4.0 behavior in place.** Live default `ANALYSIS_PIPELINE_VERSION` stays `1.4.0`.
2. **No tuning on the locked 2024 OOS TEST set.** Fit or select rules on TRAIN
   (2022) / VALIDATION (2023) only; evaluate TEST once.
3. **One hypothesis family:** H1 only (do not combine H2–H4).
4. **Predeclare** success/failure criteria before looking at TEST metrics.
5. Keep execution rules from `docs/BACKTEST_EXECUTION.md`.

## Dataset (locked package)

| Field | Value |
|-------|-------|
| Dataset ID | `xauusd_h1_oos_v1_retrospective_2022_2024` |
| Hash | `eac96d050a6bacfe879a0506143a053d4ce5ab7304b94cfbab91067211040d73` |
| TRAIN | 2022-01-02 → 2022-12-31 |
| VALIDATION | 2023-01-01 → 2023-12-31 |
| TEST | 2024-01-01 → 2024-07-11 (evaluate once) |

## Evaluation cadence (unchanged vs 1.4.0)

- lookback = 250
- stride = 4
- min_score = 70 (baseline emit floor before H1 band)
- forward_bars / cooldown as in `scripts/run_oos_validation_1_4_0.py`

## Arm H1 — implementation contract

| Field | Content |
|-------|---------|
| Hypothesis | High score/confidence bins are poorly calibrated; hard emit bands change trade mix quality |
| Mechanism | Post-analysis **emit gate** on score/confidence (`calibration_1_5_0.py`) — no DecisionEngine weight changes |
| Fit on | TRAIN corpus logged; **selection key = VALIDATION only** |
| Candidates | See `CANDIDATE_POLICIES` in `services/quant_engine/pipeline/calibration_1_5_0.py` |

### Predeclared VALIDATION selection

Promote to TEST only if a candidate has:

- expectancy ≥ 0
- profit factor ≥ 1.0
- trades ≥ 20

Tie-break: higher expectancy → higher PF → higher n → name.

If none qualify: still record diagnostic-best for the report; mark `qualified=false`
(experiment fails promotion; TEST may still be run once for documentation).

### Predeclared TEST success

- expectancy > 0
- profit factor ≥ 1.0
- total R ≥ 1.4.0 BASE total R (−22.434) − 5.0  → floor −27.434

## Runner

```bash
python scripts/run_oos_experiment_1_5_0.py --generate-fit
python scripts/run_oos_experiment_1_5_0.py --select
python scripts/run_oos_experiment_1_5_0.py --test
python scripts/run_oos_experiment_1_5_0.py --finalize
```

Artifacts: `validation_1_5_0/` + `docs/EXPERIMENT_REPORT_1.5.0.md`  
Keep `validation/` for **1.4.0** immutable.

## Related

- [PROJECT_CLOSURE_1.4.0.md](PROJECT_CLOSURE_1.4.0.md)
- [OOS_FAILURE_FORENSICS_1.4.0.md](OOS_FAILURE_FORENSICS_1.4.0.md)
- [ANALYTICAL_FREEZE.md](ANALYTICAL_FREEZE.md)

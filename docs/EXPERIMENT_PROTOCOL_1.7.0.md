# Experiment Protocol — Pipeline 1.7.0 (Arm H2)

**Status:** COMPLETE — Arm **H2** **FAILED EXPERIMENT** (see `docs/EXPERIMENT_REPORT_1.7.0.md`)  
**Frozen baseline:** 1.4.0 (do not modify)  
**Prior:** 1.5.0 H1 FAILED · 1.6.0 H3 FAILED  
**Experiment version:** `1.7.0` (TP remap only)

## Hard rules

1. Never edit 1.4.0 analysis in place.
2. Select on VALIDATION only; TEST once after lock.
3. One hypothesis family: **H2 only** (no H1/H3 combination).
4. Predeclared criteria below (same floors as H1/H3).
5. Execution stays signal_close / sl_first / costs 0 (`docs/BACKTEST_EXECUTION.md`).

## Mechanism

Keep each signal’s **original stop_loss**. Remap take-profit to:

`TP = entry ± target_rr × |entry − stop_loss|`

Baseline arm uses the original `take_profit_1` (~1.333 R from ATR 2 / 1.5).

## Candidates

See `CANDIDATE_POLICIES` in `services/quant_engine/pipeline/calibration_1_7_0.py`
(rr ∈ {baseline, 0.75, 1.0, 1.5, 2.0, 2.5, 3.0}).

## Selection / success

VALIDATION: expectancy ≥ 0, PF ≥ 1.0, n ≥ 20  
TEST: expectancy > 0, PF ≥ 1.0, total R ≥ −27.434

## Runner

```bash
python scripts/run_oos_experiment_1_7_0.py --all
```

Artifacts: `validation_1_7_0/` + `docs/EXPERIMENT_REPORT_1.7.0.md`

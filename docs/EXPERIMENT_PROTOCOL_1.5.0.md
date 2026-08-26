# Experiment Protocol — Pipeline 1.5.0 (Charter Only)

**Status:** CHARTER — not implemented  
**Frozen baseline:** 1.4.0 (do not modify)  
**Purpose:** If product reopens analytics, run **versioned** experiments without
contaminating the locked OOS verdict for 1.4.0.

This document does **not** authorize code changes. Implementation is a separate
task after explicit product approval.

## Hard rules

1. **Never edit 1.4.0 behavior in place.** Branch a new `ANALYSIS_PIPELINE_VERSION`.
2. **No tuning on the locked 2024 OOS TEST set.** Fit or select rules on TRAIN
   (2022) / VALIDATION (2023) only; evaluate TEST once.
3. **One hypothesis family per version bump** (or clearly labeled factorial
   design with predeclared arms).
4. **Predeclare** success/failure criteria before looking at TEST metrics.
5. Keep execution rules from `docs/BACKTEST_EXECUTION.md` unless the experiment
   is explicitly about exits (then version + document).

## Dataset (reuse locked package unless new ID)

| Field | Value |
|-------|-------|
| Dataset ID | `xauusd_h1_oos_v1_retrospective_2022_2024` |
| Hash | `eac96d050a6bacfe879a0506143a053d4ce5ab7304b94cfbab91067211040d73` |
| TRAIN | 2022-01-02 → 2022-12-31 |
| VALIDATION | 2023-01-01 → 2023-12-31 |
| TEST | 2024-01-01 → 2024-07-11 (evaluate once) |

If a new dataset is introduced, mint a new dataset ID + hash; do not overwrite.

## Evaluation cadence (must match or be re-declared)

Unless the experiment is specifically about cadence:

- lookback = 250
- stride = 4
- min_score = 70
- forward_bars / cooldown as in `scripts/run_oos_validation_1_4_0.py`

Changing cadence requires documenting that results are **not** comparable 1:1
to the 1.4.0 report.

## Candidate experiment arms (from forensics)

These come from `docs/OOS_FAILURE_FORENSICS_1.4.0.md`. They are **hypotheses**,
not approved product rules.

### Arm H1 — Score / confidence calibration

| Field | Content |
|-------|---------|
| Hypothesis | High score/confidence bins are poorly calibrated; remapping or thresholds change trade mix quality |
| Evidence (exploratory) | Low score bin exp &gt; high score bin on OOS forensics |
| Mechanism | DecisionEngine score/confidence mapping |
| Fit on | TRAIN (+ optional VALIDATION for threshold pick) |
| Success (predeclare example) | VALIDATION expectancy ≥ 0 and PF ≥ 1.0; then TEST must not be worse than 1.4.0 BASE by more than X R **and** show positive expectancy |
| Version impact | New pipeline version |

### Arm H2 — Exit / payoff geometry

| Field | Content |
|-------|---------|
| Hypothesis | Fixed ~1.333 R cannot overcome ~39% WR; alternate SL/TP changes breakeven WR |
| Evidence | Constant planned RR; WR &lt; ~42.9% breakeven |
| Mechanism | Signal SL/TP construction only |
| Fit on | TRAIN/VALIDATION |
| Version impact | New pipeline version |

### Arm H3 — Direction / alignment gating

| Field | Content |
|-------|---------|
| Hypothesis | Shorts and/or structure-opposed setups dominate losses |
| Evidence | Sell total R ≪ buy; opposed cells worse (small-n caveats) |
| Mechanism | Predeclared gates in DecisionEngine / signal emit |
| Fit on | TRAIN/VALIDATION only |
| Version impact | New pipeline version |

### Arm H4 — Ranking / liquidity context

| Field | Content |
|-------|---------|
| Hypothesis | Zone rank and ASSOCIATED_SWEEP labels lack predictive validity |
| Evidence | Rank-1 still negative; sweep-associated loss mass |
| Mechanism | Ranking keys or liquidity weighting |
| Version impact | New pipeline version |

### Arm H5 — Shadow / prospective (no analytical change)

| Field | Content |
|-------|---------|
| Hypothesis | Prospective accrual may differ from retrospective holdout |
| Mechanism | Run frozen **1.4.0** on newly locked prospective data |
| Version impact | **None** (still 1.4.0) |
| Note | Does not “fix” 1.4.0; only re-tests generalization |

## Recommended order

1. **H5** if prospective data can be locked (cheapest integrity check).
2. Else **H1** or **H3** as single-arm 1.5.0 (simplest DecisionEngine surface).
3. Defer **H2** / **H4** unless H1/H3 fail to move VALIDATION.

Do **not** combine all arms into one silent 1.5.0 dump.

## Required artifacts per experiment version

```text
docs/EXPERIMENT_REPORT_<version>.md
validation_<version>/
  dataset_manifest.json
  config_manifest.json
  signals.jsonl
  trades.jsonl
  metrics.json
  walk_forward.json
  reproducibility.json
```

Keep `validation/` for **1.4.0** immutable.

## Definition of done for an experiment

- [ ] Version incremented
- [ ] Golden fixtures updated
- [ ] Full test suite green
- [ ] TRAIN/VAL selection logged before TEST reveal
- [ ] TEST evaluated once
- [ ] Honest OBSERVED / INFERRED / UNKNOWN sections
- [ ] No edits to 1.4.0 analytical code paths

## Related

- [PROJECT_CLOSURE_1.4.0.md](PROJECT_CLOSURE_1.4.0.md)
- [OOS_FAILURE_FORENSICS_1.4.0.md](OOS_FAILURE_FORENSICS_1.4.0.md)
- [ANALYTICAL_FREEZE.md](ANALYTICAL_FREEZE.md)

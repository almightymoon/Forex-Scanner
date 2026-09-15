# Experiment Protocol — H5 Prospective Shadow (1.4.0)

**Status:** BLOCKED — accrual gate not met  
**Pipeline:** frozen `1.4.0` (no analytical change)  
**Checked:** 2026-09-15

## Gate (from post-2026H1 protocol)

| Requirement | Status |
|-------------|--------|
| ≥ 1,400 unique normalized H1 bars | **Fail** (332) |
| Coverage through 2026-09-30T20:00Z | **Fail** (latest 2026-07-21) |

Source: `scripts/status_xauusd_h1_post_2026h1_accrual.py`

## When unblocked

1. Lock prospective dataset ID + hash (do not overwrite retrospective OOS).
2. Run frozen 1.4.0 with identical cadence/execution as `validation/`.
3. Write `validation_h5_prospective/` + report — **does not** reverse the 1.4.0 FAILED verdict.

## Non-claims

H5 is a generalization check only. It is not a strategy fix and must not be used to retune 1.4.0.

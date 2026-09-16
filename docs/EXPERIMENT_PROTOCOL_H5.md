# Experiment Protocol — H5 Prospective Shadow (1.4.0)

**Status:** BLOCKED — accrual gate not met  
**Pipeline:** frozen `1.4.0` (no analytical change)  
**Checked:** 2026-09-16  
**Runner:** `scripts/run_h5_prospective_1_4_0.py`

## Gate (from post-2026H1 protocol)

| Requirement | Status |
|-------------|--------|
| ≥ 1,400 unique normalized H1 bars | **Fail** (1275 — need 125 more) |
| Coverage through 2026-09-30T20:00Z | **Fail** (latest 2026-09-16T12:00Z) |

Source: `scripts/status_xauusd_h1_post_2026h1_accrual.py`

**Ops note (2026-09-16):** Ingested tranche `20260916T130616Z` (+943 new bars). Quarantine tip advanced to **2026-09-16**. Still short of 1400 bars and the Sep 30 date gate. Re-export after ~Sep 30 (or whenever ≥1400 unique bars exist).

## Commands

```bash
# Accrual / gate only
PYTHONPATH=. python scripts/run_h5_prospective_1_4_0.py --status

# When gate passes — locks dataset hash + writes validation_h5_prospective/
PYTHONPATH=. python scripts/run_h5_prospective_1_4_0.py --run
```

While accruing, ingest only:

```bash
PYTHONPATH=. python scripts/ingest_xauusd_h1_post_2026h1_quarantine.py \
  --raw <XAUUSD_H1_raw.csv> \
  --metadata <XAUUSD_H1_raw.meta.csv>
```

## When unblocked

1. Lock prospective dataset ID + SHA-256 (do not overwrite retrospective OOS).
2. Run frozen 1.4.0 with identical cadence/execution as `validation/` (via paper-broker twin).
3. Write `validation_h5_prospective/` + report — **does not** reverse the 1.4.0 FAILED verdict.

## Non-claims

H5 is a generalization check only. It is not a strategy fix and must not be used to retune 1.4.0.
Leave `SCANNER_EMIT_POLICY` unset.
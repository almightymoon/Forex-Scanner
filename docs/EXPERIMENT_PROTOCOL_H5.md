# Experiment Protocol — H5 Prospective Shadow (1.4.0)

**Status:** BLOCKED — accrual gate not met  
**Pipeline:** frozen `1.4.0` (no analytical change)  
**Checked:** 2026-09-15 (re-checked same day after paper/venue work)  
**Runner:** `scripts/run_h5_prospective_1_4_0.py`

## Gate (from post-2026H1 protocol)

| Requirement | Status |
|-------------|--------|
| ≥ 1,400 unique normalized H1 bars | **Fail** (332) |
| Coverage through 2026-09-30T20:00Z | **Fail** (latest 2026-07-21) |

Source: `scripts/status_xauusd_h1_post_2026h1_accrual.py`

**Ops note (2026-09-15):** No newer MT5 post-2026H1 export is available locally beyond quarantine tranche `20260721T111152Z`. Existing `MT5-scripts/..._20260720...` re-ingest is correctly refused (immutable snapshot). `chart_csv/FXNavigators_XAUUSD_H1_first_half_2026.csv` ends 2026-04-23 (pre-gate window) and must not be force-ingested as post-2026H1.

Helper: `PYTHONPATH=. python scripts/ingest_and_check_h5.py` — discovers MT5-scripts exports, attempts ingest, prints H5 gate.

Export runbook: [MT5-scripts/README.md](../MT5-scripts/README.md) + `tools/mt5/ExportXAUUSDH1Post2026H1.mq5`.

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
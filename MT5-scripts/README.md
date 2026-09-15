# MT5 post-2026H1 exports

Drop fresh **raw + meta** pairs here, then:

```bash
PYTHONPATH=. python scripts/ingest_and_check_h5.py
# when gate passes:
PYTHONPATH=. python scripts/run_h5_prospective_1_4_0.py --run
```

## How to export (Windows + MetaTrader 5)

1. Copy `tools/mt5/ExportXAUUSDH1Post2026H1.mq5` into MT5 `Scripts/`
2. Compile and run on an XAUUSD H1 chart (symbol input default `XAUUSD.vx`)
3. Copy the produced `FXNavigators_XAUUSD_H1_post_2026H1_raw_<stamp>.csv` **and** `.meta.csv` into this folder
4. Tip must extend **past** quarantine `20260721T111152Z` (need ≥1400 unique bars through 2026-09-30T20:00Z)

## Current state

- Quarantine tip: `20260721T111152Z` (332 unique bars)
- Existing `..._20260720T020551Z` re-ingest is correctly **refused** (immutable)
- Do **not** use `chart_csv/FXNavigators_XAUUSD_H1_first_half_2026.csv` (ends Apr 2026 — wrong window)

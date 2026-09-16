# MT5 post-2026H1 exports

Drop fresh **raw + meta** pairs here, then:

```bash
PYTHONPATH=. python scripts/ingest_and_check_h5.py
# when gate passes:
PYTHONPATH=. python scripts/run_h5_prospective_1_4_0.py --run
```

## How to export (Windows + MetaTrader 5)

1. Copy updated `tools/mt5/ExportXAUUSDH1Post2026H1.mq5` into MT5 `MQL5/Scripts/`
2. Compile in MetaEditor
3. Open your **gold H1** chart (whatever the broker calls it)
4. Drag the script onto that chart
5. Inputs:
   - `InpSymbol` = **leave empty** (uses chart symbol)
   - `InpCommonFolder` = **false** (writes under this terminal’s `MQL5/Files`)
6. Click OK — watch **Toolbox → Experts** for `Acquisition complete` or an error line
7. Open the folder printed as `OPEN THIS FOLDER:`  
   (usually `…\Terminal\<ID>\MQL5\Files\`)
8. Copy both `*.csv` + `*.meta.csv` into repo `MT5-scripts/`

### If nothing appears

| Experts log says | Fix |
|------------------|-----|
| `could not select symbol` | Wrong name — leave `InpSymbol` empty on the gold chart |
| `CopyRates returned 0` / no H1 history | Tools → Options → Charts → Max bars = Unlimited; scroll chart left to load history; re-run |
| `file already exists` | Wait 1 second, run again |
| Silent / no print | Script didn’t compile or wasn’t dropped on a chart — check Navigator → Scripts |

Do **not** look only in `Common\Files` unless `InpCommonFolder=true`.

## Current state

- Quarantine tip: `20260721T111152Z` (332 unique bars)
- Existing `..._20260720T020551Z` re-ingest is correctly **refused** (immutable)
- Do **not** use `chart_csv/FXNavigators_XAUUSD_H1_first_half_2026.csv` (ends Apr 2026 — wrong window)

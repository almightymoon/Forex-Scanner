# MT5 post-2026H1 exports

Drop fresh **raw + meta** pairs here, then:

```bash
PYTHONPATH=. python scripts/ingest_and_check_h5.py
# when gate passes:
PYTHONPATH=. python scripts/run_h5_prospective_1_4_0.py --run
```

## How to export (Windows + MetaTrader 5)

Use the **repo** script `tools/mt5/ExportXAUUSDH1Post2026H1.mq5` (v1.01).

1. Copy it into MT5 `MQL5/Scripts/` (overwrite the old one)
2. Open in MetaEditor → **Compile** (must say 0 errors)
3. In Navigator → Scripts, right-click → **Refresh**
4. Open `XAUUSD.vx` H1 chart (or your gold symbol)
5. Drag script onto chart — keep defaults:
   - `InpSymbol` = `XAUUSD.vx`
   - `InpCommonFolder` = `true`
6. Files land in:  
   `C:\Users\<you>\AppData\Roaming\MetaQuotes\Terminal\Common\Files\`
7. Copy **both** `*.csv` and `*.meta.csv` into repo `MT5-scripts/`

If MetaEditor shows compile errors, you still have the broken intermediate copy — replace from the repo again.

## Current state

- Quarantine tip: `20260916T130616Z` (**1275** unique bars, latest **2026-09-16**)
- Still need **125** more unique bars + coverage through **2026-09-30**
- Older `..._20260720...` re-ingest is correctly refused (immutable)

# MT5 XAUUSD H1 Export

`ExportXAUUSDH1Benchmark.mq5` exports chart history even when MT5 for macOS does
not expose a History Center or CSV export menu.

1. Open MetaEditor from MT5.
2. Open `MQL5/Scripts` and create or paste the exporter file there.
3. Compile it.
4. In MT5, drag the script onto any chart.
5. Set the broker symbol exactly, for example `XAUUSD.vx`.
6. Keep H1 and the requested date range, then run it.
7. Read the Experts log for the output folder.

With `InpCommonFolder=true`, MT5 writes to its Common `Files` directory. The
CSV timestamps are broker-server timestamps. When preparing the benchmark,
pass the broker timezone explicitly, for example:

```bash
python scripts/prepare_xauusd_h1_benchmark.py \
  --input /path/to/FXNavigators_XAUUSD_H1.csv \
  --source WEALTHTEX_MT5 \
  --source-timezone Europe/Helsinki
```

Do not guess the broker timezone for a final benchmark. Confirm it from the
broker or by comparing a known market event with the chart timestamp.

# XAUUSD H1 Benchmark Data

This directory contains the immutable, canonical H1 candle file used by the
human swing benchmark. The file is intentionally not generated from test
fixtures.

Create it from an MT5 or vendor CSV export:

```bash
python scripts/prepare_xauusd_h1_benchmark.py \
  --input /path/to/XAUUSD_H1.csv \
  --source WEALTHTEX_MT5
```

The command writes `XAUUSD_H1.real.csv.gz`, records its SHA-256 checksum,
selects 12 non-overlapping calibration windows, and creates the human-label
manifest. Never replace this file after labeling has started. A different feed
or bar-building policy must receive a new dataset ID and benchmark version.

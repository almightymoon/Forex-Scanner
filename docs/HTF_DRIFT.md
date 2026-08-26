# HTF Drift Observability

Provider HTF series and Bar-Builder rollups from LTF may differ.
This module **detects and classifies** drift; it does **not** change analysis.

## When each source is used

| Path | HTF source for MTF trends |
|------|---------------------------|
| LIVE | Provider/collector HTF when present; rollup fills gaps (`merge_htf_bars`) |
| REPLAY / BACKTEST | Rollup from causal LTF prefix (optional injected HTF filtered as-of) |

## Why they may differ

- Provider aggregation rules vs `rollup_bars`
- Missing / corrected historical bars
- Timezone or session boundary alignment
- Incomplete forming bars
- Broker-specific OHLC

## API

```python
from services.quant_engine.pipeline import compare_htf_context, maybe_log_htf_drift

report = compare_htf_context(
    symbol="XAUUSD",
    ltf_candles=h1_prefix,
    provider_htf={"H4": provider_h4, "D1": provider_d1},
    as_of=h1_prefix[-1].timestamp,
)
```

## Classifications (`HtfDriftKind`)

| Kind | Meaning |
|------|---------|
| `MATCH` | Completed bars align (timestamp + OHLC within tolerance) |
| `EXPECTED_DIFFERENCE` | Tiny numerical OHLC delta (< 0.1% rel) |
| `MISSING_PROVIDER_DATA` | Rollup has a bar/timestamp provider lacks |
| `MISSING_ROLLUP_DATA` | Provider has a bar/timestamp rollup lacks |
| `TIMESTAMP_MISMATCH` | Same completed count, different timestamps |
| `OHLC_MISMATCH` | Same timestamp, material OHLC delta |
| `COMPLETION_MISMATCH` | Bar present but not closed as-of |
| `STRUCTURAL_DIFFERENCE` | Large count divergence |

## Telemetry

- Env: `HTF_DRIFT_TELEMETRY=true`
- Default: **off**
- Live hook: `SignalBuilder.build` → `maybe_log_htf_drift` **before** analysis
- Logs compact non-MATCH diffs (capped); no credentials / raw API payloads
- **Does not** replace provider or rollup data, alter scores, confidence, SL/TP, or fingerprints

## Causality

Unchanged: incomplete HTF bars remain unavailable; future HTF cannot affect earlier LTF fingerprints.

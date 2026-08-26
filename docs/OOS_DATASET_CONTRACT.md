# OOS Dataset Contract

**Status:** LOCKED for scanner OOS validation under pipeline **1.4.0**  
**Rule:** Once locked, **do not modify** candles because of poor results.

## Locked identity

| Field | Value |
|-------|-------|
| Dataset ID | `xauusd_h1_oos_v1_retrospective_2022_2024` |
| Symbol | `XAUUSD` |
| Timeframe | `H1` |
| Start (UTC) | `2022-01-02T22:00:00+00:00` |
| End (UTC) | `2024-07-11T04:00:00+00:00` |
| Candle count | `15368` |
| Source | `benchmarks/data/retrospective/XAUUSD/H1_2022_2024_v1/XAUUSD_H1_2022_2024.real.csv.gz` |
| Provider | `WEALTHTEX_MT5_XAUUSD_VX` (BID) |
| File hash (SHA-256) | `eac96d050a6bacfe879a0506143a053d4ce5ab7304b94cfbab91067211040d73` |
| Pipeline version for run | `1.4.0` |
| Manifest | `validation/dataset_manifest.json` / `tests/fixtures/oos/dataset_manifest.json` |

## Chronological split (declared before evaluation)

| Split | Start | End | Role |
|-------|-------|-----|------|
| Train | 2022-01-02 | 2022-12-31 | Descriptive only — **no fitting** |
| Validation | 2023-01-01 | 2023-12-31 | Descriptive only — **no fitting** |
| Test (OOS) | 2024-01-01 | 2024-07-11 | Headline evaluation |

## Quality gates

- [x] Continuous timestamps validated (weekday gaps documented, not repaired)
- [x] OHLC integrity via `load_candles_csv` + integrity report
- [x] Timezone UTC
- [x] Train/test split dates written before evaluation
- [x] Hash recorded

## Mutation policy

| Event | Action |
|-------|--------|
| Bad results | Keep dataset; report metrics |
| Data error discovered | New dataset ID + hash; document supersession |
| Silent overwrite | **Forbidden** |

## Honesty notes

- Package is a **retrospective** holdout (not prospective post-2026H1 certification).
- Swing-label `eligible_for_evaluation=false` does not block OHLC use for scanner OOS.
- Prospective post-2026H1 accrual is incomplete and was **not** substituted.

## Related

- [OOS_VALIDATION_PROTOCOL.md](OOS_VALIDATION_PROTOCOL.md)
- [OOS_VALIDATION_REPORT_1.4.0.md](OOS_VALIDATION_REPORT_1.4.0.md)
- [ANALYTICAL_FREEZE.md](ANALYTICAL_FREEZE.md)

# OOS Validation Report — Pipeline 1.4.0

Generated: 2026-08-23T21:08:21.121762+00:00

## 1. Dataset

| Field | Value |
|-------|-------|
| Dataset ID | `xauusd_h1_oos_v1_retrospective_2022_2024` |
| Provider | WEALTHTEX_MT5_XAUUSD_VX |
| Symbol | XAUUSD |
| Timeframe | H1 |
| Date range | 2022-01-02T22:00:00+00:00 → 2024-07-11T04:00:00+00:00 |
| Candle count | 15368 |
| SHA-256 | `eac96d050a6bacfe879a0506143a053d4ce5ab7304b94cfbab91067211040d73` |

## 2. Configuration

| Field | Value |
|-------|-------|
| Pipeline | `1.4.0` |
| Entry | signal_close |
| Ambiguous | sl_first |
| SL/TP | signal stop_loss / take_profit_1 |
| Spread/Slip/Comm (BASE) | 0 / 0 / 0 |
| min_score | 70 |
| lookback / stride | 250 / 4 |
| Parameter fitting | **None** |
| Config hash | `afc1f1a9beeca73fd201ca1693eb72a3ed518aac9f4113ec372cde4b555d8222` |

## 3. Split

| Split | Start | End | Role |
|-------|-------|-----|------|
| Train | 2022-01-02T22:00:00+00:00 | 2022-12-31T23:00:00+00:00 | Descriptive — no fitting |
| Validation | 2023-01-01T00:00:00+00:00 | 2023-12-31T23:00:00+00:00 | Descriptive — no fitting |
| **Test** | 2024-01-01T00:00:00+00:00 | 2024-07-11T04:00:00+00:00 | **Headline OOS** |

## 4. Overall OOS (BASELINE — OBSERVED)

| Metric | Value |
|--------|-------|
| Trades | 246 |
| Wins / Losses / BE | 95 / 151 / 0 |
| Win rate | 38.6% (approx CI [32.5, 44.7]) |
| Profit factor | 0.761 |
| Expectancy (avg R) | -0.091 |
| Total R | -22.434 |
| Max DD (R) | 30.329 |
| Max DD (pips) | 35069.46 |
| Avg winner / loser (pips) | 1006.75 / -831.97 |
| Longest losing streak | 17 |
| Longest winning streak | 6 |
| Ambiguous | 4 |

## 5. Walk-Forward

No parameter fitting. Same frozen config on chronological TEST slices.

| Window | Trades | WR% | PF | Exp | Total R | MaxDD R |
|--------|--------|-----|----|-----|---------|---------|
| WF1_2024Q1 | 112 | 42.0 | 0.929 | -0.005 | -0.5685 | 13.371 |
| WF2_2024Q2 | 121 | 35.5 | 0.68 | -0.17 | -20.5322 | 27.958 |
| WF3_2024Q3partial | 13 | 38.5 | 0.704 | -0.103 | -1.3333 | 4.667 |

## 6. Subperiod Stability

| Period | Trades | WR% | PF | Exp | Total R | MaxDD R |
|--------|--------|-----|----|-----|---------|---------|
| 2024-01 | 38 | 31.6 | 0.579 | -0.244 | -9.2632 | 13.371 |
| 2024-02 | 38 | 42.1 | 0.893 | 0.017 | 0.6535 | 5.333 |
| 2024-03 | 36 | 52.8 | 1.451 | 0.223 | 8.0411 | 7.385 |
| 2024-04 | 41 | 48.8 | 0.989 | 0.098 | 4.0363 | 6.0 |
| 2024-05 | 43 | 34.9 | 0.681 | -0.159 | -6.8294 | 9.163 |
| 2024-06 | 37 | 21.6 | 0.322 | -0.479 | -17.739 | 19.368 |
| 2024-07 | 13 | 38.5 | 0.704 | -0.103 | -1.3333 | 4.667 |

## 7. Regime Analysis

- **bearish**: n=69, WR=34.8%, PF=0.71, exp=-0.165, total_R=-11.3707
- **bullish**: n=147, WR=39.5%, PF=0.741, exp=-0.069, total_R=-10.09
- **ranging**: n=30, WR=43.3%, PF=1.104, exp=-0.032, total_R=-0.9733

## 8. Cost Sensitivity

| Scenario | Trades | WR% | PF | Exp | Total R | MaxDD R |
|----------|--------|-----|----|-----|---------|---------|
| BASELINE | 246 | 38.6 | 0.761 | -0.091 | -22.434 | 30.329 |
| LOW | 246 | 38.6 | 0.737 | -0.11 | -26.9922 | 31.778 |
| HIGH | 246 | 38.6 | 0.698 | -0.141 | -34.5715 | 38.186 |

## 9. Reproducibility

| Check | Result |
|-------|--------|
| Trade hash match | True |
| Fingerprint sample mismatches | 0/25 |
| Identical | **True** |

## 10. Leakage Audit

**PASS**

- analyze_candle_window on causal lookback ending at signal bar
- HTF via pipeline resolve_mtf_trends / completed-bar filter
- simulate_trade on post-signal bars only; sl_first
- Neutral NewsContext
- Splits/config locked before evaluation
- No parameter fitting
- Signal stride=4 and lookback=250 fixed a priori

## 11. Statistical Interpretation

**OBSERVED:** baseline metrics on locked TEST under frozen 1.4.0 + documented execution/lookback/stride.

**INFERRED:** win-rate CI; Monte Carlo trade-order resampling (median total R=-22.4006, p05=-51.1232, p95=6.435).

**UNKNOWN:** live fill quality beyond costs; news causality; unique broker IANA zone; prospective post-2026 performance.

n=246. Stride=4 reduces evaluation density vs every bar — cadence fixed before results, not tuned to outcomes.

## 12. Problems Found

- Retrospective (not prospective) OHLC package.
- Finite lookback 250 + stride 4 (evaluation design, documented).
- Weekday gaps documented in integrity report; not repaired.

## 13. Pipeline Changes

None — analytical pipeline remained frozen at 1.4.0.

## 14. Verdict

**FAILED OOS VALIDATION**

## 15. Next Task

**Closed for 1.4.0.** See `docs/PROJECT_CLOSURE_1.4.0.md`.

If product reopens analytics: follow `docs/EXPERIMENT_PROTOCOL_1.5.0.md`
(versioned experiment only — do not patch 1.4.0 silently). Optional:
prospective/shadow run of frozen 1.4.0 (arm H5) without analytical changes.

## Distribution

- Long/Short: 145/101
- HTF: {'bullish': 139, 'bearish': 107}
- Structure: {'ranging': 30, 'bullish': 147, 'bearish': 69}

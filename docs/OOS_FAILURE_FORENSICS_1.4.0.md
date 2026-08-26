# OOS Failure Forensics — 1.4.0

Generated: 2026-08-23T21:30:52.550447+00:00

**Scope:** diagnosis only. Pipeline 1.4.0 unchanged. No tuning.

> These subgroup relationships are exploratory and are not validated predictive rules. Multiple comparisons inflate false discoveries.

## 1. Frozen baseline

| Field | Value |
|-------|-------|
| Pipeline | 1.4.0 (frozen) |
| Dataset | `xauusd_h1_oos_v1_retrospective_2022_2024` |
| Hash | `eac96d050a6bacfe879a0506143a053d4ce5ab7304b94cfbab91067211040d73` |
| Test window | 2024-01-01 → 2024-07-11 |
| Lookback / stride | 250 / 4 |
| Execution | signal_close / sl_first / costs 0 |
| Parameter fitting | None |

## 2. Result verification

**Match report:** `True`

| Metric | Observed | Report | Match |
|--------|----------|--------|-------|
| Trades | 246 | 246 | True |
| Win rate | 38.6 | 38.6 | True |
| PF | 0.761 | 0.761 | True |
| Expectancy | -0.091 | -0.091 | True |
| Total R | -22.434 | -22.434 | True |
| Max DD R | 30.329 | 30.329 | True |
| Losing streak | 17 | 17 | True |

## 3. Winner vs loser analysis

Winners n=95, Losers n=151.

| Feature | Winners | Losers | Diff (W−L) |
|---------|---------|--------|------------|
| mean score | 92.5263 | 93.3642 | -0.838 |
| mean confidence | 0.8683 | 0.8661 | 0.0022 |
| mean planned R:R | 1.3333 | 1.3333 | 0.0 |
| mean stop distance | 8.0578 | 8.8013 | -0.7435 |
| mean bars held | 8.1053 | 7.9007 | 0.205 |
| mean MAE R | 0.3273 | 1.4382 | -1.1109 |
| mean MFE R | 1.6287 | 0.5549 | 1.0738 |
| % HTF ALIGNED | 88.4 | 86.1 | 2.3 |
| % structure ALIGNED | 76.8 | 76.2 | 0.6 |
| % buy | 63.2 | 56.3 | 6.9 |
| mean primary zone rank | 1.2947 | 1.2848 | 0.01 |
| mean distance_atr | 4.3568 | 3.4902 | 0.8666 |
| mean freshness_bars | 68.2947 | 55.1854 | 13.109 |

## 4. Score/confidence calibration

Predeclared bins (not outcome-optimized).

### Score

| Bin | Metrics |
|-----|---------|
| high_95_100 | n=139 | WR=38.8% | PF=0.742 | exp=-0.093 | totalR=-12.9248 | maxDD=21.018 |
| low_71_84 | n=42 | WR=45.2% | PF=0.929 | exp=0.074 | totalR=3.1189 | maxDD=5.16 |
| medium_85_94 | n=65 | WR=33.8% | PF=0.726 | exp=-0.194 | totalR=-12.6281 | maxDD=15.629 |

### Confidence

| Bin | Metrics |
|-----|---------|
| high_0.85_1.00 | n=152 | WR=38.2% | PF=0.787 | exp=-0.1 | totalR=-15.1487 | maxDD=19.801 |
| low_lt_0.60 | n=35 | WR=42.9% | PF=0.82 | exp=0.025 | totalR=0.8844 | maxDD=6.194 |
| medium_0.60_0.84 | n=59 | WR=37.3% | PF=0.655 | exp=-0.138 | totalR=-8.1697 | maxDD=11.811 |

## 5. Long vs short

| Side | Metrics |
|------|---------|
| buy | n=145 | WR=41.4% | PF=0.818 | exp=-0.028 | totalR=-4.079 | maxDD=18.757 |
| sell | n=101 | WR=34.7% | PF=0.674 | exp=-0.182 | totalR=-18.355 | maxDD=21.889 |

## 6. Structure alignment

Signal direction vs `structure_external_bias`.

| Alignment | Metrics |
|-----------|---------|
| ALIGNED | n=188 | WR=38.8% | PF=0.79 | exp=-0.073 | totalR=-13.8098 | maxDD=22.168 |
| NEUTRAL | n=30 | WR=43.3% | PF=1.104 | exp=-0.032 | totalR=-0.9733 | maxDD=6.052 |
| OPPOSED | n=28 ⚠ n<30 | WR=32.1% | PF=0.374 | exp=-0.273 | totalR=-7.651 | maxDD=11.906 |

## 7. HTF alignment

Signal direction vs `ranking_htf_trend`.

| Alignment | Metrics |
|-----------|---------|
| ALIGNED | n=214 | WR=39.3% | PF=0.78 | exp=-0.084 | totalR=-17.9332 | maxDD=24.295 |
| OPPOSED | n=32 | WR=34.4% | PF=0.626 | exp=-0.141 | totalR=-4.5008 | maxDD=8.034 |

### Combinations (structure × HTF)

| Combo | Metrics |
|-------|---------|
| S:ALIGNED|H:ALIGNED | n=164 | WR=39.6% | PF=0.815 | exp=-0.063 | totalR=-10.309 | maxDD=15.467 |
| S:ALIGNED|H:OPPOSED | n=24 ⚠ n<30 | WR=33.3% | PF=0.597 | exp=-0.146 | totalR=-3.5008 | maxDD=7.701 |
| S:NEUTRAL|H:ALIGNED | n=25 ⚠ n<30 | WR=48.0% | PF=1.356 | exp=0.068 | totalR=1.6934 | maxDD=4.052 |
| S:NEUTRAL|H:OPPOSED | n=5 ⚠ n<30 | WR=20.0% | PF=0.404 | exp=-0.533 | totalR=-2.6667 | maxDD=3.0 |
| S:OPPOSED|H:ALIGNED | n=25 ⚠ n<30 | WR=28.0% | PF=0.298 | exp=-0.373 | totalR=-9.3176 | maxDD=11.906 |
| S:OPPOSED|H:OPPOSED | n=3 ⚠ n<30 | WR=66.7% | PF=1.534 | exp=0.556 | totalR=1.6667 | maxDD=1.0 |

## 8. Liquidity relation

From re-analysis zone_context on primary same-direction zone (read-only).

| Relation | Metrics |
|----------|---------|
| ASSOCIATED_SWEEP | n=188 | WR=37.2% | PF=0.724 | exp=-0.122 | totalR=-22.9767 | maxDD=31.59 |
| NEAR_RELEVANT | n=33 | WR=39.4% | PF=0.645 | exp=-0.1 | totalR=-3.2976 | maxDD=7.034 |
| NONE | n=25 ⚠ n<30 | WR=48.0% | PF=1.469 | exp=0.154 | totalR=3.8403 | maxDD=4.826 |

## 9. FVG vs OB

| Driver | Metrics |
|--------|---------|
| fvg_and_ob | n=245 | WR=38.4% | PF=0.753 | exp=-0.097 | totalR=-23.7674 | maxDD=31.662 |
| fvg_only | n=1 ⚠ n<30 | WR=100.0% | PF=n/a | exp=1.333 | totalR=1.3333 | maxDD=0.0 |

## 10. Zone rank

Primary same-direction zone rank among soft-capped SMC zone patterns.

| Rank | Metrics |
|------|---------|
| 1 | n=202 | WR=39.1% | PF=0.788 | exp=-0.078 | totalR=-15.7373 | maxDD=25.351 |
| 2 | n=27 ⚠ n<30 | WR=29.6% | PF=0.489 | exp=-0.268 | totalR=-7.2315 | maxDD=8.898 |
| 3 | n=9 ⚠ n<30 | WR=44.4% | PF=0.879 | exp=0.014 | totalR=0.1231 | maxDD=3.0 |
| 4 | n=7 ⚠ n<30 | WR=57.1% | PF=1.144 | exp=0.202 | totalR=1.4117 | maxDD=2.0 |
| 6 | n=1 ⚠ n<30 | WR=0.0% | PF=0.0 | exp=-1.0 | totalR=-1.0 | maxDD=1.0 |

## 11. Temporal stability

| Period | Metrics |
|--------|---------|
| 2024-01 | n=38 | WR=31.6% | PF=0.579 | exp=-0.244 | totalR=-9.2632 | maxDD=13.371 |
| 2024-02 | n=38 | WR=42.1% | PF=0.893 | exp=0.017 | totalR=0.6535 | maxDD=5.333 |
| 2024-03 | n=36 | WR=52.8% | PF=1.451 | exp=0.223 | totalR=8.0411 | maxDD=7.385 |
| 2024-04 | n=41 | WR=48.8% | PF=0.989 | exp=0.098 | totalR=4.0363 | maxDD=6.0 |
| 2024-05 | n=43 | WR=34.9% | PF=0.681 | exp=-0.159 | totalR=-6.8294 | maxDD=9.163 |
| 2024-06 | n=37 | WR=21.6% | PF=0.322 | exp=-0.479 | totalR=-17.739 | maxDD=19.368 |
| 2024-07 | n=13 ⚠ n<30 | WR=38.5% | PF=0.704 | exp=-0.103 | totalR=-1.3333 | maxDD=4.667 |

| Quarter | Metrics |
|---------|---------|
| 2024Q1 | n=112 | WR=42.0% | PF=0.929 | exp=-0.005 | totalR=-0.5685 | maxDD=13.371 |
| 2024Q2 | n=121 | WR=35.5% | PF=0.68 | exp=-0.17 | totalR=-20.5322 | maxDD=27.958 |
| 2024Q3 | n=13 ⚠ n<30 | WR=38.5% | PF=0.704 | exp=-0.103 | totalR=-1.3333 | maxDD=4.667 |

## 12. Regime analysis

Canonical labels: `structure_external_bias` / signal `trend`.

| Regime (structure) | Metrics |
|--------------------|---------|
| bearish | n=69 | WR=34.8% | PF=0.71 | exp=-0.165 | totalR=-11.3707 | maxDD=14.704 |
| bullish | n=147 | WR=39.5% | PF=0.741 | exp=-0.069 | totalR=-10.09 | maxDD=27.407 |
| ranging | n=30 | WR=43.3% | PF=1.104 | exp=-0.032 | totalR=-0.9733 | maxDD=6.052 |

| HTF trend | Metrics |
|-----------|---------|
| bearish | n=107 | WR=31.8% | PF=0.606 | exp=-0.249 | totalR=-26.5895 | maxDD=29.923 |
| bullish | n=139 | WR=43.9% | PF=0.881 | exp=0.03 | totalR=4.1555 | maxDD=12.056 |

## 13. MAE/MFE

Causal path on post-signal bars only (diagnostic).

- Mean MAE (all): 1.0092 R
- Mean MFE (all): 0.9696 R
- Mean MAE (losers): 1.4382 R
- Mean MFE (losers): 0.5549 R
- Mean MAE (winners): 0.3273 R
- Mean MFE (winners): 1.6287 R

| Path tag (losers) | Count |
|------------------|-------|
| stop_out_before_favorable_excursion | 63 |
| standard_stop_loss | 54 |
| immediate_adverse_move | 35 |
| wrong_directional_bias_htf | 21 |
| target_nearly_reached_then_reversal | 13 |
| prolonged_stagnation | 10 |

## 14. Signal vs execution

| Scenario | Total R | Exp | PF |
|----------|---------|-----|----|
| BASELINE (0 costs) | -22.434 | -0.091 | 0.761 |
| LOW cost | -26.9922 | -0.11 | 0.737 |
| HIGH cost | -34.5715 | -0.141 | 0.698 |

**Signal direction / geometry dominate:** baseline total R = -22.434 with zero costs. Costs add ~12.14 R of further drag (HIGH vs BASE), but the edge is already negative at zero cost.

- Mean planned R:R: 1.3333 (constant across all 246 trades)
- Median planned R:R: 1.3333
- Share planned R:R < 1.0: 0.0
- Mean realized R | winners: 1.2751
- Mean realized R | losers: -0.9508
- **Breakeven math (OBSERVED geometry):** for fixed R:R ≈ 1.333, breakeven win rate ≈ `1 / (1 + 1.333) ≈ 42.9%`. Observed WR **38.6%** is below that threshold — negative expectancy is the arithmetic consequence of hit-rate vs payoff, not of R:R &lt; 1.

Decomposition (approximate, BASE):

| Source | Contribution |
|--------|----------------|
| Directional hit-rate vs 1.333 R payoff | Primary (BASE total R −22.43) |
| SL/TP geometry (fixed 1.333; winners ≈+1.28R, losers ≈−0.95R) | Couples with WR; not “broken RR&lt;1” |
| Execution costs | Secondary aggravator only (~−4.6R LOW, ~−12.1R HIGH vs BASE) |

## 15. Data integrity considerations

- Retrospective OHLC package — not prospective post-2026 certification dataset.
- Weekday/session gaps noted in OOS integrity; not repaired.
- Evaluation lookback=250 and stride=4 fixed a priori — reduces density vs every-bar expanding window; does not reverse the negative BASE result by itself.
- XAU pip_size=0.01 inflates max_drawdown_pips presentation; PnL R multiples use price risk and remain the primary metric.
- BASE spread/slippage/commission = 0 — research baseline; HIGH cost worsens results further.
- Broker timezone uniqueness UNKNOWN; timestamps treated as UTC-aware from source.
- NewsContext was neutral in OOS — news contribution UNKNOWN.
- These quirks do **not** invalidate the FAILED OOS conclusion under the documented protocol; they limit external generalization. Verdict remains **FAILED**, not INVALID.

## 16. Exploratory findings

- Baseline negative expectancy at zero costs (total R=−22.434) — analytical/signal failure, not cost failure.
- Long/short asymmetry: buy n=145 exp=−0.028 totalR=−4.1; sell n=101 exp=−0.182 totalR=−18.4 (shorts dominate loss mass).
- Score calibration inverted in predeclared bins: low_71_84 exp=+0.074 (n=42); medium_85_94 exp=−0.194 (n=65); high_95_100 exp=−0.093 (n=139). High-score saturation does not buy better outcomes.
- Confidence similar pattern: low_lt_0.60 least bad; high_0.85_1.00 negative (n=152).
- HTF ALIGNED is the majority (n=214) and still negative (exp=−0.084) — alignment does not rescue expectancy.
- Structure ALIGNED majority (n=188) still negative; structure OPPOSED worse but n=28 (insufficient alone).
- Liquidity: ASSOCIATED_SWEEP dominates (n=188, exp=−0.122, totalR=−23.0). NONE looks better but n=25 (insufficient).
- FVG vs OB: almost all trades are `fvg_and_ob` (n=245) — cannot attribute failure to one detector class.
- Zone rank 1 (n=202) still negative (exp=−0.078) — top rank lacks predictive edge on realized R.
- Loser paths: 63 stop-out-before-favorable; 35 immediate adverse; 13 target-nearly-reached-then-reversal; only 21 HTF-opposed among losers.
- Temporal: not a single-month fluke — Jan/May/Jun negative; Mar briefly positive; **June** worst (WR 21.6%, totalR −17.7) but Q1 also soft.
- Dual-aligned S:ALIGNED|H:ALIGNED (n=164) still exp=−0.063 — best-populated confluence cell fails.

## 17. Hypotheses for future experiments

**NOT implemented. Separate versioned experiments only.**

### H1 — Score/confidence thresholding experiment
- **Hypothesis:** Higher score/confidence bins may not improve realized R; a recalibrated mapping or hard filter might change trade mix.
- **Evidence:** See score/confidence bin tables (exploratory). Low score bin looked better here — that is **not** a validated rule.
- **Expected mechanism:** Remove low-information high-score saturation or require calibrated confidence.
- **Experiment required:** Versioned DecisionEngine / confidence mapping A/B on TRAIN only; lock before TEST.
- **Pipeline version impact:** Would require new ANALYSIS_PIPELINE_VERSION if analytical scoring changes.

### H2 — SL/TP geometry / payoff experiment
- **Hypothesis:** Fixed ~1.333 R:R cannot overcome observed ~39% WR; alternative exits might change the breakeven WR requirement.
- **Evidence:** Mean planned RR=1.3333 constant; WR 38.6% &lt; ~42.9% breakeven; mean loser R=−0.9508.
- **Expected mechanism:** Wider targets or structure-aware stops change payoff distribution.
- **Experiment required:** Separately versioned exit model; do not retune on OOS.
- **Pipeline version impact:** New pipeline version if signal SL/TP construction changes.

### H3 — Regime / HTF / short-side gating experiment
- **Hypothesis:** Shorts and/or structure-opposed cells may be systematically worse; dual alignment alone is insufficient.
- **Evidence:** Sell totalR −18.4 vs buy −4.1; S:OPPOSED|H:ALIGNED n=25 exp=−0.373 (small-n warning).
- **Expected mechanism:** Gate or down-weight opposed / short setups.
- **Experiment required:** Predeclare gates on TRAIN; evaluate once on locked TEST.
- **Pipeline version impact:** New version if DecisionEngine gating changes.

### H4 — Zone ranking / liquidity-context predictive validity experiment
- **Hypothesis:** Soft-capped zone rank and ASSOCIATED_SWEEP liquidity labels may not correlate with realized R.
- **Evidence:** Rank 1 n=202 still negative; ASSOCIATED_SWEEP carries most loss mass.
- **Expected mechanism:** Alternative ranking keys or liquidity weighting.
- **Experiment required:** Versioned ranking module comparison on TRAIN→TEST.
- **Pipeline version impact:** New version if ranking rules change.

### H5 — Prospective dataset / shadow validation
- **Hypothesis:** Retrospective OHLC + stride/lookback evaluation design may differ from live accrual.
- **Evidence:** Known evaluation quirks; FAILED OOS still holds under documented design.
- **Expected mechanism:** Prospective post-lock data reduces some dataset biases (not a strategy fix).
- **Experiment required:** Shadow/paper on prospective candles with identical 1.4.0.
- **Pipeline version impact:** None if 1.4.0 remains frozen.

## 18. What we must NOT conclude

- That filtering to low-score / low-confidence trades would improve live performance (exploratory only; multiple comparisons).
- That removing shorts or opposed setups is a proven fix (not tested out-of-sample as a rule).
- That June 2024 alone “explains” failure (Jan/May also negative; dual-aligned cell still loses).
- That costs caused the failure (BASE already negative).
- That FVG or OB alone is the culprit (245/246 are `fvg_and_ob`).
- That planned R:R &lt; 1 caused failure (share R:R&lt;1 = 0%; problem is WR below breakeven for fixed 1.333).
- That n=246 proves statistical significance of any subgroup contrast.
- That changing stride/lookback would salvage 1.4.0 without a new experiment.
- That the OOS is INVALID due to data quirks (quirks limit generalization; R-based failure remains).

## 19. Final diagnosis

**Categories:**

1. **A. Directional signal weakness** (primary)
2. **E. Confidence/score is poorly calibrated** (high score/confidence not better; exploratory inversion)
3. **F. Long/short asymmetry** (shorts carry most of total R loss)
4. **D. Ranking/context has little predictive value** (rank-1 and HTF/structure alignment still negative at scale)
5. **C. Regime dependence** (severity varies by month/regime; failure not confined to one label)
6. **I. Insufficient evidence** (for claiming any live edge or any subgroup fix)

**Not selected:** B as “poor absolute R:R&lt;1” (false here); G as primary (costs secondary); H as INVALIDATOR (quirks present, conclusion still FAILED under protocol).

OBSERVED: 246 OOS trades, WR 38.6%, PF 0.761, expectancy −0.091 R, total R −22.43, max DD 30.33 R. Zero-cost BASE already negative; HIGH cost total R −34.57 (worse). Long exp=−0.028, short exp=−0.182. Score bins low/med/high exp=+0.074/−0.194/−0.093. Worst month 2024-06 total R=−17.74 (n=37). Loser paths: mean loser MFE=0.55 R vs MAE=1.44 R. INFERRED: primary failure is directional hit-rate below the breakeven WR implied by frozen ~1.333 R payoff, with shorts and high-score saturation as exploratory aggravators — not execution friction. UNKNOWN: live fills, causal news, prospective generalization. Subgroup relationships remain exploratory (multiple comparisons).

---

## Appendix — distributions (descriptive)

- Direction: {'buy': 145, 'sell': 101}
- Session UTC: {'asia_utc': 83, 'london_utc': 45, 'ny_overlap_utc': 59, 'ny_utc': 40, 'off_hours_utc': 19}
- Month counts: {'2024-01': 38, '2024-02': 38, '2024-03': 36, '2024-04': 41, '2024-05': 43, '2024-06': 37, '2024-07': 13}
- R outcome mean/std: -0.0912 / 1.1031
- Holding bars mean: 7.9797
- News: UNKNOWN — OOS used neutral NewsContext; no causal news metadata on trades.

Pipeline confirmation: `1.4.0`
Enrichment used: `True`

# XAUUSD H1 AI-Assisted Swing Benchmark — Draft v1

## Status

- Dataset: `XAUUSD_H1_REAL_V1`
- Label origin: `AI_ASSISTED_EXPERT_DRAFT`
- Intended use: development calibration only
- Not final ground truth: independent market-structure adjudication is still required
- Samples reviewed: 12
- Confirmed swing labels: 171
- Major external: 78
- Major internal: 3
- Minor internal: 90
- Minor external: 0

## Labeling Method

The twelve 400-candle windows were reviewed as raw H1 candlestick charts with predictions hidden. A multi-scale directional-change pass was used only as an annotation aid: a 3.0 ATR reversal defined the initial structural pivot sequence, while a 4.2 ATR reversal provided an external-structure reference. Thirteen visually meaningful internal pivots omitted by the coarse pass were added manually. Every label stores the exact pivot candle and a later causal confirmation candle.

## Per-Sample Label Counts

| Sample | Regime | Labels | Major External | Major Internal | Minor Internal |
|---|---|---:|---:|---:|---:|
| XAUUSD_H1_001 | TREND_REVERSAL | 16 | 7 | 0 | 9 |
| XAUUSD_H1_002 | LOW_VOLATILITY | 14 | 10 | 0 | 4 |
| XAUUSD_H1_003 | STRONG_BEARISH_TREND | 14 | 5 | 1 | 8 |
| XAUUSD_H1_004 | TREND_REVERSAL | 12 | 4 | 0 | 8 |
| XAUUSD_H1_005 | LOW_VOLATILITY | 12 | 7 | 0 | 5 |
| XAUUSD_H1_006 | RANGE | 12 | 6 | 0 | 6 |
| XAUUSD_H1_007 | HIGH_VOLATILITY | 11 | 7 | 0 | 4 |
| XAUUSD_H1_008 | RANGE | 13 | 5 | 1 | 7 |
| XAUUSD_H1_009 | STRONG_BEARISH_TREND | 17 | 7 | 1 | 9 |
| XAUUSD_H1_010 | STRONG_BULLISH_TREND | 17 | 7 | 0 | 10 |
| XAUUSD_H1_011 | STRONG_BULLISH_TREND | 16 | 8 | 0 | 8 |
| XAUUSD_H1_012 | HIGH_VOLATILITY | 17 | 5 | 0 | 12 |

## Engine v2.0.0 Baseline

- Predictions: 550
- True positives: 157
- False positives: 393
- False negatives: 14
- Micro precision: 0.285
- Micro recall: 0.918
- Micro F1: 0.436
- Mean sample F1: 0.437
- Mean major F1: 0.246
- Mean major precision: 0.144
- Mean major recall: 0.931
- Mean relative detection delay: -5.86 bars

## Interpretation

The current engine finds most draft swings, but produces far too many signals. Its main failure mode is over-segmentation: 550 confirmed predictions versus 171 draft labels. Major-swing recall is high, while major precision is very low, which means the hierarchy classifier is promoting too many local pivots into major structure. Negative relative delay means the engine confirms earlier than the stricter draft confirmation policy; that must be reviewed rather than automatically treated as an advantage.

## Next Tuning Targets

1. Reduce false positives through stronger ATR/materiality and same-leg consolidation rules.
2. Rebuild major/minor classification around leg prominence and protected-structure relevance.
3. Rebuild internal/external classification using an explicit active dealing range.
4. Calibrate confirmation timing against the stored human-relative confirmation index.
5. Keep all twelve windows in the development split; do not call this a locked test result.

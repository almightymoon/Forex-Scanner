# XAUUSD H1 Human Swing Benchmark

## Purpose

The real benchmark is the ground truth used to tune and compare Swing Engine
versions. Synthetic fixtures remain useful for software regression, but they
must never be presented as trader ground truth.

The benchmark is a three-part immutable unit:

1. One canonical real XAUUSD H1 candle file.
2. Human swing annotations tied to exact candle indexes and prices.
3. A manifest tying samples and labels to the candle file checksum.


## Current calibration release

`benchmarks/labels/XAUUSD_H1.human.json` currently contains the first
AI-assisted expert draft across all 12 calibration windows. Its declared origin
is `AI_ASSISTED_EXPERT_DRAFT`, and its status is
`READY_FOR_HUMAN_ADJUDICATION`. It is suitable for development calibration,
error analysis, and parameter experiments, but it must not be represented as an
independently adjudicated human test set.

The draft contains 171 confirmed swing labels with exact pivot and confirmation
candles. The frozen engine-v2 baseline is stored in:

```text
benchmarks/baselines/XAUUSD_H1_ai_draft_v1_baseline.json
benchmarks/baselines/XAUUSD_H1_ai_draft_v1_summary.md
```

## 1. Prepare the real candle file

Use an H1 CSV export containing timestamp, open, high, low, close, and
optionally tick volume and spread. Both normal CSV and MT5 tab-separated export
headers are accepted.

```bash
python scripts/prepare_xauusd_h1_benchmark.py \
  --input ~/Downloads/XAUUSD_H1.csv \
  --source WEALTHTEX_MT5
```

Default outputs:

```text
benchmarks/data/real/XAUUSD/H1/XAUUSD_H1.real.csv.gz
benchmarks/labels/XAUUSD_H1.human.json
benchmarks/datasets/XAUUSD_H1.human.manifest.json
```

The preparation command validates UTC ordering and OHLC integrity, writes a
canonical compressed CSV, computes SHA-256, and selects 12 non-overlapping
400-candle calibration charts:

- 2 strong bullish trends
- 2 strong bearish trends
- 2 ranges
- 2 high-volatility periods
- 2 low-volatility periods
- 2 reversal periods

Each chart has 50 candles of left context, 300 labelable candles, and 50
candles of right context.

## 2. Label blindly

```bash
python scripts/annotate_swings.py benchmarks/labels/XAUUSD_H1.human.json
```

The local annotation studio opens at `http://127.0.0.1:8765`. It does not show
algorithm predictions. It can review both human drafts and the protected
AI-assisted expert draft. Select the pivot candle, select the first confirmation
candle, classify the swing, and save the draft.

Each annotation records:

- Exact pivot index, UTC timestamp, and candle high or low
- High/low direction
- Major/minor hierarchy
- Internal/external scope
- Confirmation status and confirmation candle
- Strength from 1 to 5
- Quality from 0 to 100
- Confidence from 0 to 1
- Tags, notes, annotator, and review state

The labeler creates a timestamped backup before every save.

## 3. Validate labels

```bash
python scripts/validate_human_benchmark.py \
  benchmarks/labels/XAUUSD_H1.human.json
```

The validator checks the candle checksum, exact timestamp and pivot price,
labelable boundaries, confirmation order, metadata ranges, duplicate IDs, and
final-scope rules.

## 4. Run the real benchmark

```bash
python scripts/run_benchmark_suite.py \
  --manifest benchmarks/datasets/XAUUSD_H1.human.manifest.json \
  --version 2.0.0 \
  --output benchmarks/reports/XAUUSD_H1_human_v2.json
```

Draft calibration thresholds are zero so baseline reports can be generated
without pretending the engine has passed a production standard. Acceptance
thresholds are frozen only after labels are adjudicated.

## Label policy

### Pivot

A high label must equal the exact high of the selected candle. A low label must
equal its exact low. The UI fills price and timestamp automatically.

### Confirmation

The confirmation candle is the earliest bar at which a competent analyst could
have identified the swing without future knowledge. It must occur after the
pivot. Pivot accuracy and detection delay are evaluated separately.

### Major versus minor

A major swing anchors or materially changes H1 structure. A minor swing is a
meaningful local pivot but does not define the principal dealing range.

### Internal versus external

An external swing defines the active outer H1 range or protected structure. An
internal swing exists inside that range. Final adjudicated labels must not use
`NEUTRAL`.

### Exclude noise

Do not label every fractal. A valid swing terminates a meaningful directional
leg and produces a structurally relevant reaction. Equal highs/lows are first
liquidity clusters; individual touches are labeled only when they produce
separate meaningful reactions.

## Governance

- Do not display predictions during first-pass labeling.
- Do not overwrite `.human.json` with engine-generated labels.
- Preserve raw analyst files and create an adjudicated release.
- Never tune on locked test samples.
- A changed data feed, checksum, timezone policy, or label policy requires a new
  benchmark version.
## 5. Chronological development split

The 12 calibration windows are now divided chronologically, with no overlap:

```text
TRAIN:      XAUUSD_H1_001 through XAUUSD_H1_008
VALIDATION: XAUUSD_H1_009 through XAUUSD_H1_012
TEST:       none yet
```

Parameters may be selected on `TRAIN` only. `VALIDATION` is evaluated after
selection. Because there is no locked `TEST` split and the labels remain an
AI-assisted draft, every result is development evidence rather than production
certification.

## 6. Tune the v2.1 structural profile

```bash
python scripts/tune_xauusd_h1.py
```

The command refuses manifests containing a locked `TEST` split. It selects the
reversal threshold by maximum TRAIN F1 subject to a TRAIN recall floor, then
selects the Major/External prominence threshold using TRAIN structural F1. Only
after both choices are fixed does it report VALIDATION performance.

The current selected profile is:

```text
Structural reversal:          2.80 ATR
Major/External prominence:    5.00 ATR
Prominence weights:           70% incoming leg, 30% confirming reversal
Adaptive whole-window tuning: disabled
Candidate availability:       enforced
Pivot validity through confirmation: enforced
```

Report:

```text
benchmarks/reports/XAUUSD_H1_v2_1_tuning_search.json
benchmarks/reports/XAUUSD_H1_v2_1_tuning_summary.md
```

### Development result

| Split | Precision | Recall | F1 | FP | FN |
|---|---:|---:|---:|---:|---:|
| TRAIN | 0.8148 | 0.8462 | 0.8302 | 20 | 16 |
| VALIDATION | 0.9474 | 0.8060 | 0.8710 | 3 | 13 |
| All calibration windows | 0.8606 | 0.8304 | 0.8452 | 23 | 29 |

Compared with frozen v2.0 on the same 12 windows, false positives fell from
393 to 23. Recall decreased from 0.9181 to 0.8304, which is the deliberate cost
of suppressing local fractal noise. These values must not be promoted to
production acceptance thresholds until independent adjudication and a new
locked test set are complete.

## 7. Tune the v2.2 recursive hierarchy

v2.2 keeps the v2.1 location detector unchanged and tunes only the second-level
Major/Minor hierarchy:

```bash
python scripts/tune_xauusd_h1_hierarchy.py
```

Selection uses TRAIN samples only. A profile is eligible only when:

```text
TRAIN Major External precision >= 0.90
Worst TRAIN sample semantic F1 >= 0.50
```

The eligible profile with the highest aggregate TRAIN full-semantic F1 is
selected. VALIDATION is evaluated exactly once after the hierarchy and
provisional thresholds are frozen.

Selected profile:

```text
First-level reversal threshold:  2.80 ATR (frozen v2.1)
Hierarchy reversal threshold:    5.00 ATR
Provisional prominence:          5.00 ATR
Scope policy:                    higher-order major -> external
```

Report:

```text
benchmarks/reports/XAUUSD_H1_v2_2_hierarchy_search.json
benchmarks/reports/XAUUSD_H1_v2_2_hierarchy_summary.md
```

### Hierarchy result

| Validation metric | v2.1 | v2.2 |
|---|---:|---:|
| Location F1 | 0.8710 | 0.8710 |
| Full semantic F1 | 0.5806 | 0.7258 |
| Tier accuracy | 0.6852 | 0.8334 |
| Scope accuracy | 0.6667 | 0.8519 |
| Major External precision | 0.6296 | 0.9474 |
| Major External F1 | 0.6296 | 0.7826 |

The location prediction count, false positives, and false negatives are
identical. The gain comes entirely from recursive hierarchy classification.

`PROVISIONAL_MAJOR` labels are intentionally revisable. Only
`CONFIRMED_MAJOR` labels have a `hierarchy_confirmation_index` and should be
treated as frozen higher-order structure by downstream modules.

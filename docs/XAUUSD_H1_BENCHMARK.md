# XAUUSD H1 Human Swing Benchmark

## Purpose

The real benchmark is the ground truth used to tune and compare Swing Engine
versions. Synthetic fixtures remain useful for software regression, but they
must never be presented as trader ground truth.

The benchmark is a three-part immutable unit:

1. One canonical real XAUUSD H1 candle file.
2. Human swing annotations tied to exact candle indexes and prices.
3. A manifest tying samples and labels to the candle file checksum.

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
algorithm predictions. Select the pivot candle, select the first confirmation
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

# Swing Detection Engine — Technical Documentation (Sprint 2)

## Architecture

```mermaid
flowchart TD
    MD[Market Data Providers] --> DC[Data Collector]
    DC --> RT[(Raw Tick Storage dc_ticks)]
    RT --> BB[Deterministic Bar Builder]
    BB --> BARS[OHLCV Bars M1-D1]
    BARS --> SE[Swing Engine]
    SE --> SW[Detected Swings]
    SW --> VIZ[Visualization]
    SW --> EVAL[Benchmark Evaluation]
    EVAL --> RPT[JSON / CSV Reports]
```

## Module Map

| Module | Path | Responsibility |
|--------|------|----------------|
| Data Collector | `services/data_collector/` | Download, validate, persist ticks + candles |
| Bar Builder | `services/bar_builder/` | Deterministic UTC bar aggregation + rollup |
| Swing Engine | `swing_engine/` | **Only swing detection implementation** (versioned) |
| Market structure consumer | `services/quant_engine/swing_analysis.py` | Consumes `SwingEngine` for BOS/CHoCH/trend context |
| Scanner service | `services/scanner_service/` | Pipeline orchestration — imports swing_engine |
| Config | `config/swing_detection.yaml` | All thresholds |

## Swing Engine Pipeline

```
Bars → Pivots → Noise Filter → ATR Validation → Leg Validation
     → Confirmation → Scoring → Scope/Tier/Confidence → Output
```

### Public API

```python
from swing_engine import SwingEngine, SwingVisualizer, SUPPORTED_VERSIONS
from shared.types.models import Timeframe

# Versioned engine (default v1.1.0)
engine = SwingEngine(version="1.1.0")
result = engine.detect(bars, symbol="EURUSD", timeframe=Timeframe.H1)

result.swings              # List[DetectedSwing]
result.artifacts           # PipelineArtifacts — intermediate stages
result.performance         # PerformanceMetrics — runtime / throughput
result.stage_logs          # Per-stage counts for debugging

# Convenience helper (returns swing list only)
from swing_engine import detect_swings
swings = detect_swings(bars)

# Full result with artifacts + metrics
result = SwingEngine(version="1.0.0").detect(bars, symbol="EURUSD")
```

### Versioning

| Version | Description |
|---------|-------------|
| `1.0.0` | Baseline — strict pivots, legacy defaults |
| `1.1.0` | **Default** — equal-level pivots, expanded filters, tier scoring, protected levels |

Profiles in `config/swing_detection.yaml` under `version_profiles`.

```python
from swing_engine import SwingEngine, SUPPORTED_VERSIONS

v1 = SwingEngine(version="1.0.0").detect(bars)
v11 = SwingEngine(version="1.1.0").detect(bars)
```

## Algorithm (Sprint 2)

### Pivot Detection
- Configurable left/right lookback, equal-high/low tolerance, min pivot strength
- Optional body-extreme mode; pivot strength score (wick + body vs ATR)

### Filtering (independent, configurable)
- Noise: candle distance, pip distance, ATR movement, spread, volatility
- Consolidation and insignificant pullback rejection
- ATR validation and leg validation (optional same-direction legs)

### Confirmation
- Hold pivot for `min_candles` without violation
- Optional: displacement ATR, structure break, internal structure break, retracement
- Outputs: pivot candle, confirmation candle, delay, reasoning

### Strength Scoring
- Components: leg size, ATR, reaction, duration, volume, wick ratio, displacement, trend quality
- Returns **raw score** and **normalized score** (0–100)

### Classification
- **Major/Minor:** weighted tier score (leg ATR, strength, reaction, confirmation, duration)
- **Internal/External:** protected highs/lows, dealing range midpoint, HH/LL progression

### Versioning (API)

Implementations live under `swing_engine/versions/`. Compare engines without replacing prior logic:

```python
from swing_engine import SwingEngine, SUPPORTED_VERSIONS

v1 = SwingEngine(version="1.0.0").detect(bars)
# v2 = SwingEngine(version="2.0.0").detect(bars)  # when added
```

### Pipeline Artifacts

`PipelineArtifacts` stores intermediate results for debugging:

| Field | Description |
|-------|-------------|
| `pivot_candidates` | Raw pivot detections |
| `noise_filtered` / `noise_rejected` | After noise filter |
| `atr_validated` / `atr_rejected` | After ATR validation |
| `leg_validated` / `leg_rejected` | After leg validation |
| `confirmed_swings` / `unconfirmed_swings` | Post-confirmation |
| `atr_series` | ATR values aligned to bars |

### Performance Metrics

Each `engine.detect()` run records:

- Runtime (ms) per symbol/timeframe
- Bars processed per second
- Swings detected per second
- Peak memory (MB)

### Interactive Visualization

```python
from pathlib import Path
from swing_engine import SwingEngine, SwingVisualizer

result = SwingEngine().detect(bars, symbol="EURUSD")
SwingVisualizer().render_debug_html(result, bars, Path("debug/swing_debug.html"))
```

The HTML debugger shows candlesticks, candidate pivots, confirmed/rejected swings,
major/minor and internal/external coloring, confidence on hover, confirmation markers,
and optional ATR overlay.

```bash
PYTHONPATH=. python scripts/render_swing_debug.py --symbol EURUSD --output debug.html
```

### Chart overlay API

```python
viz = SwingVisualizer().build(bars, swings, artifacts=result.artifacts, window_start=..., window_end=...)
```

### DetectedSwing Fields

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | datetime | Pivot bar open (UTC) |
| `price` | float | Swing price level |
| `direction` | HIGH / LOW | Swing direction |
| `tier` | MAJOR / MINOR | Importance classification |
| `scope` | INTERNAL / EXTERNAL / NEUTRAL | Structure position |
| `confirmed` | bool | Passed confirmation rules |
| `confirmation_index` | int | Bar where confirmed |
| `confirmation_delay` | int | Bars from pivot to confirmation |
| `strength` | 1–5 | Institutional significance |
| `confidence` | 0–1 | Detection confidence |
| `metadata` | dict | Leg ATR, scope score, components |

## Bar Builder

```python
from services.bar_builder import BarBuilder

builder = BarBuilder("EURUSD", Timeframe.M1)
bars = builder.from_ticks(tick_tuples)  # (ts, bid, ask, vol)
candles = builder.to_candles(bars)

# All timeframes from M1 ticks
all_tf = BarBuilder.build_all_timeframes("EURUSD", ticks)
```

**Guarantees:** UTC alignment, deterministic output, gap metadata on missing bars, no swing logic.

## Data Collection

- **10 FX symbols** configured in `config/data_collector.yaml`
- **Raw ticks** stored append-only in `dc_ticks` (immutable — duplicates ignored)
- **Dukascopy** provider persists ticks during download via `DataDownloader`

## Benchmark Evaluation (Sprint 2)

```bash
# Single version
PYTHONPATH=. python scripts/benchmark_swings.py --symbol EURUSD --timeframe H1 --regime trend

# Compare versions
PYTHONPATH=. python scripts/benchmark_swings.py --compare-versions 1.0.0 1.1.0 --labels benchmarks/labels/EURUSD_H1.regression.json

# Visual debugger
PYTHONPATH=. python scripts/render_swing_debug.py --version 1.1.0 --bars 120 --output debug/swing.html
```

### Metrics
Precision, Recall, F1, FP/FN, detection delay, price/time error, major/external precision/recall, average confidence/strength, repainting rate.

### Reports
JSON, CSV, Markdown summary, HTML version-comparison charts.

Regression baseline: `benchmarks/labels/EURUSD_H1.regression.json`

### Ground Truth Format

```json
{
  "swings": [
    {
      "pivot_index": 42,
      "timestamp": "2025-01-03T14:00:00+00:00",
      "price": 1.0856,
      "direction": "HIGH",
      "tier": "MAJOR",
      "scope": "EXTERNAL"
    }
  ]
}
```

## Configuration

All parameters in `config/swing_detection.yaml`:

```yaml
pivot:
  left_lookback: 3
  right_lookback: 3
confirmation:
  min_candles: 2
  delay_bars: 2
classification:
  major_min_atr_multiple: 1.2
  major_min_strength: 4
```

Per-timeframe overrides under `timeframe_overrides`.

## Testing

```bash
PYTHONPATH=. python -m unittest discover -s tests/test_swing_engine_pkg -p 'test_*.py' -v
PYTHONPATH=. python -m unittest discover -s tests/swing_detection -p 'test_*.py' -v
PYTHONPATH=. python -m unittest discover -s tests/integration -p 'test_*.py' -v
```

Key test modules:
- `test_scoring.py` — tier/scope/confidence
- `test_edge_cases.py` — equal highs, gaps, regimes
- `test_benchmark_regression.py` — committed label regression

## Developer Notes

- **Single implementation:** all swing detection logic lives in `swing_engine/` only
- **Consumers:** `services/quant_engine/swing_analysis.py` imports swing_engine
- **No repaint:** confirmed swings depend only on bars through `confirmation_index`
- **No magic numbers:** all thresholds in YAML (`version_profiles` + `timeframe_overrides`)
- **Default version:** `1.1.0`

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | Sprint 1 | Initial pipeline, artifacts, debugger scaffold |
| 1.1.0 | Sprint 2 | Equal-level pivots, expanded filters/strength, tier scoring, protected scope, decision timeline, benchmark reports |

## Future Integration

| Module | Consumes |
|--------|----------|
| Market Structure | `DetectedSwing.tier`, `scope`, confirmed highs/lows |
| BOS / CHoCH | External major swings as break references |
| Liquidity | Equal-level clusters from swing chain |
| Order Blocks | Last opposing candle before major displacement |
| FVG | Index gaps between confirmed swings |
| Decision Engine | `strength`, `confidence` as features |

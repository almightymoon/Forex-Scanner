# Swing Detection Engine — Sprint 1 Technical Documentation

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
| Swing Engine | `swing_engine/` | Standalone swing detection (versioned) |
| Legacy shim | `scanner/swing_detection/` | Backward-compatible pipeline |
| Config | `config/swing_detection.yaml` | All thresholds |

## Swing Engine Pipeline

```
Bars → Pivots → Noise Filter → ATR Validation → Leg Validation
     → Confirmation → Scoring → Scope/Tier/Confidence → Output
```

### Public API

```python
from swing_engine import detect_swings, SwingEngine, SwingVisualizer

swings = detect_swings(bars)  # List[DetectedSwing]

engine = SwingEngine()
result = engine.detect(bars, symbol="EURUSD", timeframe=Timeframe.H1)

viz = SwingVisualizer().build(bars, swings, window_start=..., window_end=...)
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

## Benchmark Evaluation

```bash
PYTHONPATH=. python scripts/benchmark_swings.py --symbol EURUSD --timeframe H1
```

```python
from swing_engine.evaluation import SwingBenchmarkEvaluator, write_json_report, write_csv_report

report = SwingBenchmarkEvaluator().evaluate(predicted, ground_truth, "EURUSD")
write_json_report(report, Path("benchmarks/reports/eurusd.json"))
write_csv_report(report, Path("benchmarks/reports/eurusd.csv"))
```

### Metrics

- Precision, Recall, F1
- False Positives / False Negatives
- Detection Delay (bars)
- Price Error (pips)
- Time Error (bars)
- Major Swing Precision / Recall
- External Swing Precision / Recall

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
PYTHONPATH=. python -m unittest discover -s tests/swing_engine -p 'test_*.py' -v
PYTHONPATH=. python -m unittest discover -s tests/bar_builder -p 'test_*.py' -v
PYTHONPATH=. python -m unittest discover -s tests/integration -p 'test_*.py' -v
PYTHONPATH=. ./scripts/test.sh
```

## Future Integration

| Module | Consumes |
|--------|----------|
| Market Structure | `DetectedSwing.tier`, `scope`, confirmed highs/lows |
| BOS / CHoCH | External major swings as break references |
| Liquidity | Equal-level clusters from swing chain |
| Order Blocks | Last opposing candle before major displacement |
| FVG | Index gaps between confirmed swings |
| Decision Engine | `strength`, `confidence` as features |

## Developer Notes

- **No repaint:** confirmed swings depend only on bars through `confirmation_index`
- **No magic numbers:** all thresholds in YAML
- **Backward compat:** `scanner.swing_detection` and `services.quant_engine.swing` remain functional
- **Version:** `swing_engine.__version__` = `1.0.0`

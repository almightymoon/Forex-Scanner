# Market Data → Bar Builder → Swing Detection Pipeline

This document describes the **canonical production path** as implemented in the
repository. It supersedes conflicting claims in older architecture notes where
they disagree with the code.

## Canonical flow

```text
MT5 export / Dukascopy / Twelve Data / Polygon
        ↓
Raw market data (ticks or OHLC)
        ↓
Normalization + OHLC integrity (UTC, symbol, timeframe)
        ↓
OHLC bar storage (`candles` / `dc_candles`)
        ↓
Bar Builder (`services/bar_builder`) — deterministic UTC aggregation
        ↓
Swing Detection Engine (`swing_engine`, versioned; live default 2.3.0)
        ↓
Market Structure / SMC / Decision Engine (downstream; out of scope here)
```

### Environment roles

| Mode | Data source | Simulated allowed? |
|------|-------------|--------------------|
| **Development** | Fixtures, SimulatedProvider when opted in | Yes — `ENABLE_SIMULATED_DATA=true` |
| **Testing** | Fixtures / replay CSV / benchmark packages | Yes (test harness) |
| **Production** | Real providers only (`ENVIRONMENT=production\|prod\|live`) | **Hard-blocked** |

Simulation is never inferred from `ENVIRONMENT`. Production + simulation raises
`SimulatedDataForbiddenError` at provider startup (`shared/config/market.py`).

## Dual live paths (intentional, not duplicates of the same layer)

1. **Collector path (historical / offline):**  
   `services/data_collector` → validate → `dc_candles` / `dc_ticks` → bar builder  
   Providers: MT5, Dukascopy (disabled by default in `config/data_collector.yaml`).

2. **API market-data path (live scanner):**  
   `services/market_data_service` → Twelve Data → Polygon failover  
   Optional `CollectorFirstProvider` prefers collector DB when populated.

Benchmark / research path uses MT5 MQ5 exporters under `tools/mt5/` into CSV.

## OHLC integrity

Shared checks live in `shared/market_data/ohlc_integrity.py`:

- Positive OHLC; `high >= open/close`; `low <= open/close`; `high >= low`
- Duplicate timestamps rejected
- Out-of-order timestamps flagged
- Gaps recorded explicitly — **no artificial candles are manufactured**

Collector `DataValidator` remains the stricter persistence gate (spreads, spikes).
Market-data service validator delegates series filtering to the shared module.

## Timeframes

Supported: `M1 M5 M15 M30 H1 H4 D1 W1`.

Primary scanner/benchmark TFs: `M5 M15 H1 H4 D1`.

Rollup (`rollup_bars` / `BarBuilder.build_all_timeframes`):

```text
M1 → M5 → M15 → M30 → H1 → H4 → D1 → W1
```

Rules: open = first, high = max, low = min, close = last, volume summed.  
UTC bucketing; **W1 opens Monday 00:00 UTC**.

## Swing engine (actual behavior)

- **Package:** `swing_engine/` only (do not reimplement pivots elsewhere).
- **Versions:** `1.0.0` … `2.3.0`; `DEFAULT_VERSION` / live `SCAN_SWING_VERSION` = **2.3.0**.
- **Pipeline:** context → pivots → filters → ATR/leg → **confirmation** → score → hierarchy → metadata.
- **Candidate vs confirmed:** unconfirmed pivots remain candidates until confirmation rules pass using **only bars at or after the pivot** (`confirmation.py`). Historical replay uses prefixes `bars[:i+1]`.
- **Metadata per swing:** pivot timestamp, confirmation timestamp/index/delay, price, direction, strength, quality, `algorithm_version` on `DetectionResult.version`.
- **Repainting:** lifecycle tracks invalidated candidates; confirmed swings are not rewritten by future bars in causal mode.

Full module map: `docs/SWING_DETECTION.md`.

## Benchmark methodology

| Split | Years | Use |
|-------|-------|-----|
| Development | 2015–2021 | Training / engineering |
| Validation | 2022–2023 | Model selection |
| Locked test | 2024–2026 | Final evaluation only |

Implemented in `swing_engine/dataset_splits.py`. Tuning against locked test raises.

Existing XAUUSD packages (window TRAIN/VAL, 2026H1 locked accrual) remain valid;
year splits are the **cross-symbol** protocol when multi-year CSVs exist.

### Metrics

Precision, recall, F1, FP, FN, confirmation delay, price deviation, major/external
semantic metrics — `SwingBenchmarkEvaluator`.

### CLI

```bash
# Synthetic self-check (no ground truth → exit 2 with clear message)
python -m swing_engine --symbol EURUSD --timeframe H1

# Real CSV + labels
python -m swing_engine --csv path.csv --labels path.json --version 2.3.0

# Locked year split (evaluation only)
python -m swing_engine --benchmark swing --dataset locked_test \
  --csv path.csv --labels path.json --purpose evaluate

# Legacy suite runner
python scripts/run_benchmark_suite.py
python scripts/benchmark_swings.py --symbol EURUSD --timeframe H1 --labels ...
```

### Ground truth status

Many XAUUSD label packs are **AI-assisted drafts awaiting human adjudication**.
When labels are missing, the CLI reports:

```text
Benchmark blocked: ground-truth annotations are not available.
```

Do not fabricate F1 scores.

## Persistence

| Table | Role |
|-------|------|
| `candles` / `dc_candles` | OHLC storage |
| `swings` | Versioned swing records (`algorithm_version`, source + confirmation timestamps) |
| `market_structure_events` | Causal BOS/CHOCH rows (`swing_engine_version`) |

Migrations: `database/migrations/001_swings.sql`, `002_market_structure_events.sql`.

Downstream structure analysis: [`MARKET_STRUCTURE_ENGINE.md`](MARKET_STRUCTURE_ENGINE.md).

## Tests

```bash
.venv/bin/python -m pytest -q \
  tests/bar_builder \
  tests/data_collector \
  tests/market_data \
  tests/swing_detection \
  tests/integration/test_swing_pipeline.py \
  tests/pipeline \
  tests/quant_engine/test_market_structure_*.py
```

## What remains incomplete

1. Human-adjudicated multi-symbol ground truth for locked 2024–2026 years.
2. Enabling MT5/Dukascopy collector providers for production ops.
3. Live broker execution (Phase 2 — out of scope).

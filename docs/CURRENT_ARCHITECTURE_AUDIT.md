# Current Architecture Audit

**Date:** 2026-08-23  
**Scope:** Source-traced integrity audit (not roadmap claims).  
**Pipeline version:** `ANALYSIS_PIPELINE_VERSION = 1.0.0`

This document records what the code actually does after the Scanner Integrity Audit & Production Hardening v1 pass.

---

## Canonical component table

| Component | Canonical implementation | Consumers | Duplicate implementations | Status |
|-----------|--------------------------|-----------|---------------------------|--------|
| Swing | `swing_engine/` + `obtain_confirmed_swings` / `build_scan_structure` (`swings/boundary.py`, v2.3.0) | DataLoader, pipeline, DecisionEngine, SMC | Deprecated `build_zigzag_swings` / `find_swings` in `swing_analysis.py` | COMPLETE |
| Market Structure | `analyze_structure` → `StructureSnapshot` (`market_structure/detector.py`) | FeatureExtractor, SMC, confluence, MTF bias | Legacy zigzag structure helpers | INTEGRATED |
| Liquidity | `analyze_liquidity` → `LiquiditySnapshot` (`liquidity/analyzer.py`) | FeatureExtractor, LiquidityEngine, confluence | SMC `_detect_liquidity_sweeps` + session tags | INTEGRATED / DUPLICATED detect |
| FVG | Detect: `SMCEngine._detect_fvg`; Score: `FairValueGapEngine` | DecisionEngine, confluence | scanner_service shim only | PARTIAL (last-N heuristic) |
| Order Blocks | Detect: `SMCEngine._detect_order_blocks`; Score: `OrderBlockEngine` | DecisionEngine, confluence | scanner_service shim only | PARTIAL (last-N heuristic) |
| Trend | `TrendEngine` | DecisionEngine | scanner_service shim | COMPLETE |
| Momentum | `decision/engines/momentum.py` | DecisionEngine | shim | COMPLETE |
| Volatility | `decision/engines/volatility.py` | DecisionEngine | shim | COMPLETE |
| MTF | Live: DataLoader structure bias + EMA fallback; Score: `MultiTimeframeEngine` | DecisionEngine | Backtest H1 EMA stub only | PARTIAL in backtest |
| SMC Confluence | `smc_confluence/engine.py` → `SMCContextSnapshot` | DecisionEngine (explain/warn) | Does not replace scorers | INTEGRATED |
| Decision | `quant_engine/decision/engine.py` `DecisionEngine.evaluate` | SignalBuilder, Replay, Backtest, pipeline | scanner_service re-exports | COMPLETE |
| Signal | `shared.types.models.ScannerSignal` | API, validation, notifications | TrackedSignal / TradeResult adapters | COMPLETE |
| Market Data | `market_data_service` + optional collector-first | DataLoader, Replay | Synthetic candle_builder | INTEGRATED |
| Bar Builder | `bar_builder/BarBuilder` + rollup | Tick/Dukascopy ingest, tests | **Not** on live scan hot path | PARTIAL (ingest-only) |
| Analysis Pipeline | `quant_engine/pipeline/analyze_candle_window` | Replay, Backtest, tests | Prior ad-hoc copies in replay/backtest (removed) | COMPLETE |
| Execution sim | `backtesting_service/execution.py` | BacktestEngine | Validation SL-first mirrors policy | INTEGRATED |
| Validation | `validation_engine` file store | SignalBuilder register | No Postgres production store | PARTIAL |
| Setup Intelligence | `setup_intelligence/historical_matcher.py` | DecisionEngine (evidence only) | — | INTEGRATED (live confidence adjust OFF) |
| News | `news_service` | DataLoader live | Backtest uses neutral stub | PARTIAL historically |

---

## Call graphs (actual)

### LIVE

```
API /scanner/live
 → ScannerPipeline.scan_all
   → DataLoader.load (OHLC provider/collector — not BarBuilder)
     → compute_all
     → build_scan_structure (swings + structure once)
     → SMCEngine.detect_all
     → MTF fetch + structure bias
     → NewsService
   → SignalBuilder → DecisionEngine.evaluate → ScannerSignal
   → DB / notifications / optional validation register
```

### REPLAY / BACKTEST

```
candles[:i+1]
 → analyze_candle_window  (canonical)
   → indicators → swings → structure → SMC → DecisionEngine
 → (backtest only) simulate_trade → metrics
```

### VALIDATION

```
ScannerSignal → SignalValidator.register → TrackedSignal (JSON file)
 → evaluate_open_signals on later scans → win/loss (SL-first)
 → report metrics
```

### SMC inside Decision

```
StructureSnapshot + LiquiditySnapshot + patterns + MTF
 → per-engine scores
 → structure_policy (score/confidence)
 → build_smc_context (warnings + explainability; not primary score)
 → ScannerSignal
```

---

## Ownership — market data

| Concern | Owner |
|---------|-------|
| Raw ticks / provider OHLC | `data_collector` + `market_data_service` providers |
| Normalized `Candle` model | `shared.types.models.Candle` |
| TF aggregation from ticks | `bar_builder` (ingest path) |
| What Quant Engine sees | Pre-built `list[Candle]` prefixes |
| Who may construct bars for scan | Providers/collector — **not** DecisionEngine |

---

## Status legend used above

- **COMPLETE** — production path uses it; tests cover core behaviour  
- **INTEGRATED** — wired into DecisionEngine / pipeline  
- **PARTIAL** — exists but incomplete vs product intent  
- **DUPLICATED** — more than one detection path still callable  
- **DEPRECATED** — marked deprecated, still importable  
- **BROKEN** — incorrect behaviour (fixed in this pass where listed)  
- **UNKNOWN** — depends on deployment config

# Current Architecture

Authoritative post-audit architecture. Prefer this over older roadmap diagrams when they conflict.

## Canonical analytical flow

```text
Candle[] (causal prefix)
        │
        ▼
analyze_candle_window()          ← ANALYSIS_PIPELINE_VERSION
  • compute_all (indicators)
  • build_scan_structure         ← SCAN_SWING_VERSION 2.3.0
  • SMCEngine.detect_all
  • DecisionEngine.evaluate
        │
        ▼
AnalysisBundle / ScannerSignal
        │
   ┌────┼────┐
   ▼    ▼    ▼
 LIVE REPLAY BACKTEST
              │
              ▼
         simulate_trade()   ← execution only (costs / SL-first)
              │
              ▼
         PerformanceMetrics
```

Live still loads candles via `DataLoader` (market data + MTF + news) then enters
the same DecisionEngine. Replay and Backtest call `analyze_candle_window`
directly so analytical fingerprints match for the same window.

## What is intentionally not on the live path

- Tick → `BarBuilder` aggregation (ingest/collector concern)
- Broker order routing
- SMC confluence as a second scorer (context/explain only)
- Live confidence multiplication from historical forward outcomes

## Signal contract

One analytical signal: **`ScannerSignal`**.

Adapters:

- `TrackedSignal` — validation outcomes  
- `TradeResult` / `SimulatedTrade` — backtest fills  
- `AnalysisBundle.analytical_fingerprint` — equivalence comparisons  

Version metadata lives under `market_features.pipeline_version`,
`market_features.swing_version`, and `market_features.algorithm_versions`.

## Backtest execution (summary)

See also `docs/BACKTEST_EXECUTION.md`.

| Topic | Rule |
|-------|------|
| Entry | Signal bar **close** |
| SL/TP | Next bars only |
| Ambiguous bar | **SL first** (conservative) |
| Costs | Optional spread / slippage / commission (default 0) |
| News | Neutral stub unless causal calendar injected |
| MTF | Caller map or H1 EMA stub — not full HTF fetch |

## Related docs

- [CURRENT_ARCHITECTURE_AUDIT.md](CURRENT_ARCHITECTURE_AUDIT.md)
- [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md)
- [BACKTEST_EXECUTION.md](BACKTEST_EXECUTION.md)
- [SMC_CONFLUENCE_ENGINE.md](SMC_CONFLUENCE_ENGINE.md)
- [MARKET_DATA_SWING_PIPELINE.md](MARKET_DATA_SWING_PIPELINE.md)

# Current Architecture Audit

**Date:** 2026-08-24 (HTF trend + analytical freeze)  
**Pipeline version:** `ANALYSIS_PIPELINE_VERSION = 1.4.0`

## Canonical component table

| Component | Canonical implementation | Consumers | Duplicate implementations | Status |
|-----------|--------------------------|-----------|---------------------------|--------|
| Swing | `obtain_confirmed_swings` / `build_scan_structure` v2.3.0 | pipeline | deprecated zigzag | COMPLETE |
| Market Structure | `analyze_structure` | pipeline, DE, SMC, zone ranking | — | COMPLETE |
| Liquidity | `analyze_liquidity` → snapshot → patterns | pipeline, SMC, DE, zone ranking | SMC detectors **removed** | COMPLETE |
| FVG / OB | `detect_fvg_zones` / `detect_order_block_zones` | pipeline, SMC | last-N methods **removed** | COMPLETE (lifecycle v1) |
| Zone ranking | `zones/context` + `zones/ranking` | SMC pattern adapters | — | COMPLETE (v1) |
| MTF | `resolve_mtf_trends` + HTF contract | pipeline | EMA stub removed from backtest default | INTEGRATED |
| Decision | `DecisionEngine.evaluate` | pipeline | — | COMPLETE |
| Analysis pipeline | `analyze_candle_window` | Live SignalBuilder, Replay, Backtest | DataLoader no longer runs analysis | COMPLETE |
| Signal | `ScannerSignal` | API / validation | adapters | COMPLETE |

## Call graphs

### LIVE

```
DataLoader.load → candles + htf_bars + news
SignalBuilder.build → analyze_candle_window → ScannerSignal
```

### REPLAY / BACKTEST

```
prefix → analyze_candle_window (HTF rollup) → signal
backtest → simulate_trade
```

## Ownership — market data

Unchanged: providers/collector own OHLC; Bar Builder owns rollup; Quant Engine consumes `list[Candle]` only.

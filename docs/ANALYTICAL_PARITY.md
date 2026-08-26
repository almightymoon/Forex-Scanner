# Analytical Parity

**Pipeline version:** `1.4.0`  
**Invariant:** Same available market information → same canonical analysis → same decision → same signal. Only execution/accounting may differ.

## Paths

### LIVE

```text
DataLoader (data only)
  • primary candles (provider/collector)
  • HTF series fetch (M15/H4/D1 when available)
  • news context
        ↓
SignalBuilder
  • analyze_candle_window(candles, htf_bars=…, news=…)
        ↓
ScannerSignal
```

### REPLAY / BACKTEST

```text
historical candle prefix candles[:i+1]
        ↓
analyze_candle_window(
  htf_bars=None → Bar Builder rollup + causal filter
  or injected htf_bars filtered as-of last bar
)
        ↓
ScannerSignal
(backtest only → simulate_trade)
```

## HTF data contract

| Rule | Definition |
|------|------------|
| Representation | `dict[str, list[Candle]]` keyed by TF value |
| Construction | Provider series preferred; gaps filled by `rollup_bars` |
| Availability | HTF bar open at `t` with duration `D` is available iff `as_of >= t + D` |
| Incomplete bars | Excluded via `filter_completed_htf` |
| Trends | `resolve_mtf_trends` → structure external bias, else EMA20/50 |

Module: `services/quant_engine/pipeline/mtf_context.py`

## Liquidity ownership

| Role | Owner |
|------|-------|
| Detection | Liquidity Engine v1 (`analyze_liquidity`) |
| Pattern atoms for scoring | `patterns_from_liquidity_snapshot` |
| SMC | Consumes snapshot only — **no** liquidity detector methods remain |

## FVG / OB ownership

| Role | Owner |
|------|-------|
| Detection + lifecycle | `detect_fvg_zones` / `detect_order_block_zones` |
| Canonical sets on bundle | `AnalysisBundle.fvg_zones` / `ob_zones` |
| Context + ranking | `zones/context.py` + `zones/ranking.py` (consumer only) |
| Ranking HTF trend | `select_ranking_htf_trend(resolve_mtf_trends(...))` — nearest higher TF |
| Pattern atoms for scoring | `patterns_from_fvg_zones` / `patterns_from_ob_zones` (ranked, soft-capped) |
| SMC | Consumes zone sets + snapshots — **no** parallel FVG/OB detector methods |

See [FVG_OB_LIFECYCLE.md](FVG_OB_LIFECYCLE.md), [ZONE_RANKING.md](ZONE_RANKING.md), [ANALYTICAL_FREEZE.md](ANALYTICAL_FREEZE.md), [HTF_DRIFT.md](HTF_DRIFT.md).

## Analysis vs execution

| Layer | Live | Replay | Backtest |
|-------|------|--------|----------|
| Analysis | `analyze_candle_window` | same | same |
| Execution | n/a (alert only) | n/a | `simulate_trade` |

## Compatibility

- `ScanContext` still exposes indicators/patterns/structure after `SignalBuilder.build` for strategy/event bus.
- `DataLoader.smc_engine` DI slot retained but unused for analysis.
- Pipeline version stamped on `market_features.pipeline_version`.

## Tests

- `tests/integrity/test_analytical_parity.py` — live↔canonical fingerprint, HTF causality, liquidity SoT
- `tests/integrity/test_pipeline_integrity.py` — metrics, ambiguous fills, structure no-lookahead
- `tests/quant_engine/test_fvg_ob_lifecycle.py` — causal zones, mitigation, parity, no lookahead
- `tests/quant_engine/test_htf_trend_ranking.py` — HTF injection, causality, golden fixture, reproducibility
- `tests/fixtures/golden/xauusd_h1_gold240_t04_w6.json` — frozen signal regression

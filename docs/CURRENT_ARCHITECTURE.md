# Current Architecture

Authoritative post-parity architecture (pipeline **1.4.0**).

## Canonical analytical flow

```text
DATA PREPARATION (live only networking)
  candles + optional htf_bars + news
        │
        ▼
analyze_candle_window()          ← ANALYSIS_PIPELINE_VERSION 1.4.0
  • compute_all
  • build_scan_structure         ← SCAN_SWING_VERSION 2.3.0
  • analyze_liquidity (once)
  • detect_fvg_zones / detect_order_block_zones (causal lifecycle)
  • resolve_mtf_trends → select_ranking_htf_trend
  • SMCEngine.detect_all
      – BOS/CHOCH
      – context-aware FVG/OB ranking (HTF trend injected) → soft-capped patterns
      – liquidity patterns
  • DecisionEngine.evaluate (reuses liquidity_snapshot + mtf_trends)
        │
        ▼
AnalysisBundle / ScannerSignal
  (includes fvg_zones, ob_zones, liquidity_snapshot)
        │
   ┌────┼────┐
   ▼    ▼    ▼
 LIVE REPLAY BACKTEST
              │
              ▼
         simulate_trade()
```

## Live vs research

| Concern | Live | Replay/Backtest |
|---------|------|-----------------|
| Candle source | DataLoader / providers | Historical series / fixture |
| HTF | Provider fetch + rollup fill | Rollup from LTF prefix (or injected) |
| News | Calendar service | Neutral stub unless injected |
| Analysis | Same pipeline | Same pipeline |

## Related docs

- [ANALYTICAL_PARITY.md](ANALYTICAL_PARITY.md)
- [HTF_DRIFT.md](HTF_DRIFT.md)
- [FVG_OB_LIFECYCLE.md](FVG_OB_LIFECYCLE.md)
- [ZONE_RANKING.md](ZONE_RANKING.md)
- [ANALYTICAL_FREEZE.md](ANALYTICAL_FREEZE.md)
- [OOS_VALIDATION_PROTOCOL.md](OOS_VALIDATION_PROTOCOL.md)
- [OOS_DATASET_CONTRACT.md](OOS_DATASET_CONTRACT.md)
- [FVG_OB_LIMITATIONS.md](FVG_OB_LIMITATIONS.md)
- [VALIDATION_PERSISTENCE.md](VALIDATION_PERSISTENCE.md)
- [CURRENT_ARCHITECTURE_AUDIT.md](CURRENT_ARCHITECTURE_AUDIT.md)
- [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md)
- [BACKTEST_EXECUTION.md](BACKTEST_EXECUTION.md)
- [PROJECT_CLOSURE_1.4.0.md](PROJECT_CLOSURE_1.4.0.md)
- [OOS_VALIDATION_REPORT_1.4.0.md](OOS_VALIDATION_REPORT_1.4.0.md)
- [OOS_FAILURE_FORENSICS_1.4.0.md](OOS_FAILURE_FORENSICS_1.4.0.md)
- [EXPERIMENT_PROTOCOL_1.5.0.md](EXPERIMENT_PROTOCOL_1.5.0.md)

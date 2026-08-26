# Implementation Status

Updated after **project closure** of analytical pipeline **1.4.0** (OOS + forensics complete).

| Module | Implementation | Integration | Tests | Production readiness | Known issues | Next action |
|--------|----------------|-------------|-------|----------------------|--------------|-------------|
| Canonical pipeline | `analyze_candle_window` 1.4.0 | Live + Replay + Backtest | Strong | **Frozen — OOS closed** | Failed OOS expectancy | See 1.5.0 charter |
| HTF / MTF | Causal resolve + ranking select | Ranking + DE | Yes | Frozen | Provider≠rollup possible | Drift telemetry (ops) |
| Zone ranking | Lexicographic; HTF trend injected | SMC patterns | Yes | Frozen | Fallback if HTF short | — |
| FVG / OB lifecycle | Causal zone sets | Canonical | Yes | Frozen | No expire/invalidate | — |
| Liquidity | Engine SoT | All paths | Yes | Frozen | — | — |
| DecisionEngine | Frozen weights | Pipeline | Yes | Frozen | Poor OOS calibration (forensics) | Experiment only |
| OOS validation | Locked artifacts | Research | Yes | **Complete** | Retrospective holdout | Immutable `validation/` |
| Failure forensics | Diagnostic script | Research | N/A | Complete | Exploratory subgroups | Do not convert to filters |

## Behavioral note

**1.3.0 → 1.4.0:** `trend_alignment` uses `select_ranking_htf_trend(resolve_mtf_trends(...))` (nearest higher TF). Ranking key order unchanged. Formation/lifecycle/DE weights unchanged.

## Analytical freeze + closure

- Freeze contract: [ANALYTICAL_FREEZE.md](ANALYTICAL_FREEZE.md)
- Closure: [PROJECT_CLOSURE_1.4.0.md](PROJECT_CLOSURE_1.4.0.md)
- OOS report: [OOS_VALIDATION_REPORT_1.4.0.md](OOS_VALIDATION_REPORT_1.4.0.md) — **FAILED OOS VALIDATION**
- Forensics: [OOS_FAILURE_FORENSICS_1.4.0.md](OOS_FAILURE_FORENSICS_1.4.0.md)
- Next analytics (optional): [EXPERIMENT_PROTOCOL_1.5.0.md](EXPERIMENT_PROTOCOL_1.5.0.md) — charter only

## Remaining gaps (non-analytical / Phase 2)

1. Validation JSON multi-host unsafe.
2. Provider vs rollup HTF divergence (observable).
3. Live broker execution (Phase 2).
4. Any edge recovery requires a **new** pipeline version under the 1.5.0 experiment protocol — do not patch 1.4.0.

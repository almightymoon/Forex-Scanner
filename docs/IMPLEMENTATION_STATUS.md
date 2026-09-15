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
- Experiment 1.5.0 H1: [EXPERIMENT_REPORT_1.5.0.md](EXPERIMENT_REPORT_1.5.0.md) — **FAILED**
- Experiment 1.6.0 H3: [EXPERIMENT_REPORT_1.6.0.md](EXPERIMENT_REPORT_1.6.0.md) — **FAILED**
- Experiment 1.7.0 H2: [EXPERIMENT_REPORT_1.7.0.md](EXPERIMENT_REPORT_1.7.0.md) — **FAILED**
- Experiment 1.8.0 H4: [EXPERIMENT_REPORT_1.8.0.md](EXPERIMENT_REPORT_1.8.0.md) — **PASSED** (provisional; TEST n=18)
- H5 prospective: [EXPERIMENT_PROTOCOL_H5.md](EXPERIMENT_PROTOCOL_H5.md) — **BLOCKED** (accrual)
- Scoreboard: [EXPERIMENT_SCOREBOARD.md](EXPERIMENT_SCOREBOARD.md)

## Remaining gaps (non-analytical / Phase 2)

1. ~~Validation JSON multi-host unsafe.~~ → DB-backed `validation_outcomes`.
2. Provider vs rollup HTF divergence (observable).
3. ~~Paper broker path (opt-in).~~ → [PAPER_BROKER.md](PAPER_BROKER.md) / `PAPER_BROKER_ENABLED`.
4. Live broker venue APIs (Phase 2 remainder).
5. Optional: paper-shadow `h4_rank1_liquidity_none` — see [H4_PAPER_SHADOW.md](H4_PAPER_SHADOW.md) (`scripts/paper_shadow_h4.py`).
6. H5 when post-2026H1 accrual completes — runner ready: `scripts/run_h5_prospective_1_4_0.py`.
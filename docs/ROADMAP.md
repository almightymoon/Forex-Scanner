# FX Navigators Scanner — Project Roadmap

This document is the master plan from **current state (~50%)** to a production-ready
institutional market-structure scanner. Work is organized into sprints with clear
dependencies.

## Current State (v2.0.0 production freeze)

| Component | Status | Location |
|-----------|--------|----------|
| Swing Engine | ✅ v2.0.0 default | `swing_engine/` |
| Human-review benchmarks | ✅ fractal ground truth | `benchmarks/datasets/manifest.json` |
| Score breakdown studio | ✅ weighted points panel | `swing_engine/visualization.py` |
| Benchmark history + version table | ✅ | `swing_engine/regression.py` |
| Confidence calibration | ✅ | `swing_engine/calibration.py` |
| BOS-ready structure metadata | ✅ | `swing_engine/structure_metadata.py` |
| Parameter optimizer (major focus) | ✅ | `scripts/optimize_human_labels.py` |
| BOS / CHoCH | ⏳ Not started | — |
| Liquidity engine | ⏳ Not started | — |
| Order blocks / FVG | ⏳ Not started | — |
| Decision engine (live) | 🟡 Partial | `services/scanner_service/` |
| Live broker execution | ⏳ Phase 2 | — |

---

## Architecture Layers

```
Data Layer          services/data_collector, services/bar_builder
        ↓
Swing Layer         swing_engine/          ← v2.0.0 PRODUCTION FREEZE
        ↓
Structure Layer     market_structure/      ← Sprint 5–6
        ↓
Liquidity Layer     liquidity/             ← Sprint 7
        ↓
Signal Layer        scanner_service/       ← Sprint 8–9
        ↓
Decision Layer      decision_engine/       ← Sprint 10
        ↓
Validation Layer    validation + paper     ← Ongoing
```

**Rule:** Each layer only consumes outputs from the layer below. Never re-implement
swing detection outside `swing_engine/`.

---

## Sprint 5 — Market Structure (BOS + CHoCH)

**Goal:** Detect breaks of structure and changes of character using MTF swing context.

### Deliverables
- [ ] `services/quant_engine/market_structure/bos.py`
  - Input: `DetectedSwing` + `MTFSwingContext`
  - Output: `BOSEvent` (direction, broken level, swing ref, bar index)
- [ ] `services/quant_engine/market_structure/choch.py`
  - First structural failure after trend — uses parent trend from MTF
- [ ] Config: `config/market_structure.yaml`
- [ ] Tests against labeled BOS/CHoCH fixtures (EURUSD + XAUUSD H1)
- [ ] Studio overlay: BOS/CHoCH markers on swing debug HTML

### Success criteria
- BOS only fires on **external major** swings or protected levels
- CHoCH requires HTF trend alignment score > 0.6
- Zero repainting: events commit only after confirmation bar closes

---

## Sprint 6 — Trend + Session Context

**Goal:** Institutional trend definition tied to swing hierarchy.

### Deliverables
- [ ] `TrendEngine` consuming MTF swings (not raw candles)
- [ ] Session-aware trend (Asia range vs London expansion)
- [ ] Trend state: `BULLISH | BEARISH | RANGING | TRANSITIONING`
- [ ] Attach `trend_context` to each swing in studio inspector
- [ ] Benchmark: trend label accuracy vs manual review

---

## Sprint 7 — Liquidity Engine

**Goal:** Map equal highs/lows, session highs/lows, and sweep events.

### Deliverables
- [ ] `LiquidityLevel` model (price, type, session, sweep_count)
- [ ] Equal-high/low clustering from swing chain
- [ ] Session liquidity (Asia/London/NY highs and lows)
- [ ] Sweep detection (already partial in quality score — promote to first-class)
- [ ] Feed `parent_liquidity` in `MTFSwingContext` from real engine (not extrema proxy)
- [ ] Studio layer: liquidity pools + sweep markers

---

## Sprint 8 — Order Blocks + Fair Value Gaps

**Goal:** SMC-style zones anchored to confirmed major swings.

### Deliverables
- [ ] Order block: last opposing candle before displacement swing
- [ ] FVG: 3-candle imbalance between confirmed swings
- [ ] Zone lifecycle: `FRESH → TESTED → MITIGATED → INVALID`
- [ ] Quality gate: only zones from swings with `quality_score >= 60`
- [ ] Config: `config/smc.yaml`

---

## Sprint 9 — Scanner Pipeline Integration

**Goal:** Wire structure + liquidity + zones into the live scanner.

### Deliverables
- [ ] Unified `MarketFeatures` snapshot per symbol/TF
- [ ] Scanner daemon consumes `swing_engine` v1.3+ only
- [ ] WebSocket push: swing confirmed, BOS, CHoCH, liquidity sweep
- [ ] API endpoints in `apps/api/` for structure state
- [ ] Dashboard cards for structure summary

---

## Sprint 10 — Decision Engine v2

**Goal:** Score trade setups from structure confluence (not indicators alone).

### Deliverables
- [ ] Confluence scorer: trend + BOS + liquidity sweep + OB/FVG + session
- [ ] Entry/SL/TP from structure (not fixed pip distances)
- [ ] Explainability per signal (mirror swing studio pattern)
- [ ] Paper validation loop: `SignalValidator` + swing paper log unified
- [ ] Backtest integration via `services/backtesting_service/`

---

## Sprint 11 — Performance + Scale

**Goal:** `100 symbols × 8 timeframes < 1 second` detection pass.

### Deliverables
- [ ] Incremental ATR/pivot cache (avoid full re-run on new bar)
- [ ] Parallel symbol detection (multiprocessing or async batch)
- [ ] `scripts/bench_swing_performance.py` in CI with budget assertion
- [ ] Memory profiling for 10k-bar windows
- [ ] Production metrics export (Prometheus-style counters)

**Current baseline** (run `scripts/bench_swing_performance.py`):
~500 bars/symbol on single core — optimization required for 100×8 target.

---

## Sprint 12 — Production Hardening

**Goal:** Ship-ready quality bar.

### Deliverables
- [ ] Human-labeled benchmark sets: 5 symbols × 3 TFs × 3 regimes (45 sets)
- [ ] Optimizer CI: weekly param sweep, auto-commit best if F1 improves
- [ ] Live data validation: Dukascopy/OANDA feed → paper log → weekly review
- [ ] Alerting: regression email/Slack on CI failure
- [ ] Documentation: operator runbook, config tuning guide
- [ ] Security review on API + data paths

---

## Ongoing: Measurement Discipline

Every commit answers (via CI + dashboard):

| Question | Tool |
|----------|------|
| Did precision improve? | `benchmarks/reports/regression_dashboard.html` |
| Did delay improve? | Same + `average_detection_delay_bars` |
| Did repainting increase? | `artifacts.repainting_stats` |
| Which symbols got worse? | Dashboard filter by symbol |
| Are params optimal? | `scripts/optimize_swings.py` |

### Commands

```bash
# Full benchmark + history
PYTHONPATH=. python scripts/benchmark_swings.py --symbol XAUUSD --compare-versions 1.2.0 1.3.0

# Studio with replay
PYTHONPATH=. python scripts/replay_swings.py --symbol XAUUSD --studio debug/studio.html

# Performance sweep
PYTHONPATH=. python scripts/bench_swing_performance.py

# Parameter search
PYTHONPATH=. python scripts/optimize_swings.py --labels benchmarks/labels/XAUUSD_H1.manual.json

# Tests
PYTHONPATH=. python -m pytest tests/swing_detection -q
```

---

## Version History

| Version | Sprint | Highlights |
|---------|--------|------------|
| 1.0.0 | 1 | Baseline pipeline, artifacts |
| 1.1.0 | 2 | Equal pivots, tier scoring, benchmark framework |
| 1.2.0 | 3 | Adaptive, quality, explainability, XAUUSD |
| 1.3.0 | 4 | Lifecycle, replay, MTF context, studio, optimizer, CI |
| 2.0.0 | 5–6 | BOS/CHoCH + trend (planned) |

---

## Estimated Completion

| Milestone | Est. effort | Cumulative |
|-----------|-------------|------------|
| Sprint 5–6 (BOS/CHoCH/Trend) | 2–3 weeks | 60% |
| Sprint 7–8 (Liquidity/OB/FVG) | 2–3 weeks | 75% |
| Sprint 9–10 (Scanner/Decision) | 3–4 weeks | 90% |
| Sprint 11–12 (Scale/Production) | 2–3 weeks | 100% |

**Total remaining:** ~10–13 weeks focused development to production-ready scanner.

---

## What NOT to build yet

- Broker execution / live trading (Phase 2)
- AI/ML swing prediction (deterministic engine first)
- Duplicate swing logic outside `swing_engine/`
- New trading concepts before BOS/CHoCH benchmarks pass

The swing engine is the foundation. Everything downstream gets easier once
Sprint 5–6 structure detection is solid and benchmarked.

# FX Navigators Scanner — Project Roadmap

This document is the master plan toward a production-ready institutional
market-structure scanner. Status reflects the **structure-studio-mtf** cutover
(Market Structure Engine v1 + decision/confluence + MTF structure bias).

## Current State

| Component | Status | Location |
|-----------|--------|----------|
| Swing Engine | ✅ v2.3.0 default | `swing_engine/` |
| Market Structure Engine v1 | ✅ causal BOS/CHoCH | `services/quant_engine/market_structure/` |
| Unified scan structure path | ✅ | `swings/boundary.py` + DataLoader |
| Structure regime + confluence | ✅ wired into DecisionEngine | `regime.py`, `confluence.py`, `structure_policy.py` |
| MTF structure bias (H4/D1) | ✅ structure-preferred | `mtf_bias.py`, DataLoader |
| Studio BOS/CHoCH overlays | ✅ | `studio.py` + `SwingVisualizer` |
| Live-path smoke (real CSV) | ✅ | `scripts/smoke_structure_live_path.py` |
| Liquidity / OB / FVG engines | 🟡 present, deepen next | `liquidity/`, `order_blocks/`, `fvg/` |
| Decision engine (live) | 🟡 structure-aware | `services/quant_engine/decision/` |
| Live broker execution | ⏳ Phase 2 | — |

---

## Architecture Layers

```
Data Layer          services/data_collector, services/bar_builder
        ↓
Swing Layer         swing_engine/          ← v2.3.0 DEFAULT
        ↓
Structure Layer     market_structure/      ← v1 DONE (causal BOS/CHoCH)
        ↓
Liquidity Layer     liquidity/             ← next focus
        ↓
Signal Layer        scanner_service/       ← structure-aware scan path
        ↓
Decision Layer      decision/              ← regime + confluence + HTF bias
        ↓
Validation Layer    validation + paper     ← Ongoing
```

**Rule:** Each layer only consumes outputs from the layer below. Never re-implement
swing detection outside `swing_engine/`. Live path must not rediscover pivots via
zigzag helpers.

---

## Done — Market Structure v1

- [x] Causal `analyze_structure(candles, confirmed_swings)`
- [x] Unified confirmed-swing boundary (`SCAN_SWING_VERSION = 2.3.0`)
- [x] FeatureExtractor / TrendEngine / SMC consume `StructureSnapshot`
- [x] Live-safe `score_structure_event(..., allow_lookahead=False)`
- [x] Regime classification + setup confluence in decisions
- [x] `DEFAULT_VERSION = 2.3.0`
- [x] Studio overlays for BOS/CHoCH + structure regime
- [x] MTF structure bias (H4/D1) into `mtf_trends` + decision policy

### Smoke

```bash
.venv/bin/python scripts/smoke_structure_live_path.py \
  --csv chart_csv/FXNavigators_XAUUSD_H1.csv --tail 500 \
  --html debug/xauusd_structure_smoke.html
```

---

## Next — Liquidity depth (priority)

**Goal:** First-class liquidity pools and sweeps that score against external bias.

### Deliverables
- [x] Typed `LiquidityLevel` / `LiquidityMap` / sweep quality models
- [x] Build pools from SMC equals + structure equals + session tags
- [x] Sweep quality vs structure bias (continuation vs stop-hunt)
- [x] Feed confluence from liquidity map (equals + sweeps)
- [x] Studio payload helper for pool lines + sweep markers
- [ ] HTML studio toggle wired into SwingVisualizer (follow-up)
- [ ] Paper-scan E2E audits on real XAUUSD

---

## Next — Session / OB–FVG quality

- [ ] Session-aware trend (Asia range vs London expansion)
- [ ] OB/FVG strength gated by structure event proximity
- [ ] Paper-scan E2E on real XAUUSD with structure HTML audits

---

## Later — Execution

- [ ] Live broker execution (Phase 2)
- [ ] Broader retirement of legacy zigzag compatibility shims

---

## Historical sprints (superseded by v1)

Earlier roadmap items that listed separate `bos.py` / `choch.py` modules are
**superseded** by the unified Market Structure Engine v1 detector. Keep this
section only for archaeology; do not re-open those tickets.

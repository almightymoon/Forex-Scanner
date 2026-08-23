# Implementation Status

Authoritative module status after Scanner Integrity Audit & Production Hardening v1 (2026-08-23).

| Module | Implementation | Integration | Tests | Production readiness | Known issues | Next action |
|--------|----------------|-------------|-------|----------------------|--------------|-------------|
| Market data service | Provider factory + validation | Live DataLoader | Partial | Staging-ready; prod depends on provider keys | Sim forbidden in prod env | Keep collector-first reads |
| Data collector | Daemon + BI5 | Optional read path | Limited | Partial | Historical API gaps for replay | Harden historical range API |
| Bar builder | Tick→bar + rollup | Ingest only | Yes | OK for ingest | Not on live scan path | Document; don’t dual-path scan |
| Swing engine | v2.3.0 confirmed | Canonical via boundary | Strong | Ready | Legacy zigzag still importable | Quarantine deprecated APIs |
| Market structure | Causal StructureSnapshot | Decision + SMC + confluence | Strong | Ready | — | Keep as SoT |
| Liquidity v1 | LiquiditySnapshot | Features + engine | Yes | Ready | Dual detect vs SMC sweeps | Prefer analyzer; slim SMC sweeps |
| FVG / OB detect | SMCEngine heuristics | Scored in DE | Moderate | Research-grade | Last-N only | Defer rewrite |
| Trend / Mom / Vol | Engines | DE | Yes | Ready | — | — |
| MTF | Live structure bias | DE | Moderate | Partial in BT | Backtest EMA stub | Optional HTF series inject |
| SMC confluence | Context snapshot | Explain/warn | Yes | Ready as context | Not a scorer | Optional policy gating later |
| Decision engine | 100-pt aggregator | Live/replay/BT | Strong | Ready | — | Keep single evaluate |
| Canonical pipeline | `analyze_candle_window` | Replay + BT | Yes | Ready | Live still uses DataLoader prelude | Optionally route live through it |
| Replay | Session frames | API | Light | OK for demo | Collector historical weak | Equivalence tests exist |
| Backtest | Walk-forward + execution | API | Metrics unit + integrity | Research-ready | No broker; news stub | Keep metrics honest |
| Validation | File OutcomeStore | Live register | Light | MVP | Not multi-host safe | Postgres store later |
| Setup intelligence | Historical matcher | Evidence on signal | Yes | OK | Live confidence adjust disabled | Offline research flag |
| News | Calendar service | Live | Light | Partial historically | Revised calendars may leak | Document conservative mode |
| Strategy / billing / AI | Present | Peripheral | Mixed | Out of scope here | — | Do not expand now |
| Dashboard / API | FastAPI + Next | Live scan | Mixed | Staging | — | Reliability pass later |

## Hardening completed in this pass

- Canonical `analyze_candle_window` shared by replay/backtest
- Backtest metrics: profit factor, expectancy, avg R (fixed broken avg_rr)
- Ambiguous SL/TP → SL-first (documented + tested)
- Optional spread/slippage/commission on fills
- Live historical confidence multiplier disabled
- Historical matcher `as_of_index` causal bound
- Pipeline / algorithm versions on `market_features`
- Integrity + golden fixture tests

## Explicit remaining debt

1. Dual liquidity detection (analyzer vs SMC)  
2. Backtest MTF not full HTF structure bias  
3. News not causally reconstructed for history  
4. Validation persistence is local JSON  
5. FVG/OB detection still heuristic last-N  
6. Live path duplicates some prelude work vs `analyze_candle_window` (same DecisionEngine)  
7. Bar builder unused by live scan (by design for now)

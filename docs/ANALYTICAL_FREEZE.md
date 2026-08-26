# Analytical Freeze

**Frozen pipeline version:** `ANALYSIS_PIPELINE_VERSION = 1.4.0`  
**Effective:** 2026-08-24 (HTF trend injection into zone ranking)

This document marks the analytical contract as **frozen**.

**OOS status:** complete — verdict **FAILED OOS VALIDATION**  
(see `docs/OOS_VALIDATION_REPORT_1.4.0.md`, `docs/PROJECT_CLOSURE_1.4.0.md`).

Do **not** amend 1.4.0 behavior to chase that result.

## Frozen components

| Area | Frozen artifact |
|------|-----------------|
| Swing definitions | `SCAN_SWING_VERSION` / confirmed-swing contract |
| BOS / CHoCH | Market Structure Engine v1 event rules |
| Liquidity | Liquidity Engine v1 pools / sweeps |
| FVG formation | 3-candle imbalance in `detect_fvg_zones` |
| FVG lifecycle | ACTIVE / PARTIALLY_FILLED / MITIGATED |
| OB formation | Displacement + 1.5× impulse confirm |
| OB lifecycle | ACTIVE / TOUCHED / MITIGATED |
| MTF / HTF causality | `resolve_mtf_trends` + completed-bar filter |
| Zone ranking order | lifecycle → structure → liquidity → trend → distance → freshness → zone_id |
| Trend source for ranking | `select_ranking_htf_trend` on resolved MTF map |
| DecisionEngine weights | `scoring.yaml` / V2 scoring config as loaded |
| Signal contract | `ScannerSignal` fields produced by DecisionEngine |
| Execution assumptions | Documented in OOS protocol (not part of analysis) |

## Change control

Any future analytical change **must**:

1. Increment `ANALYSIS_PIPELINE_VERSION`
2. Update golden fixtures under `tests/fixtures/golden/`
3. Re-run parity + golden regression tests
4. Document behavioral impact in `docs/IMPLEMENTATION_STATUS.md` and release notes

## Explicitly out of scope for 1.4.0

- New indicators / SMC concepts
- Ranking coefficient tuning
- DecisionEngine weight optimization
- FVG/OB formation redesign
- Additional detectors
- Silent patches after FAILED OOS

Post-closure experiments must use a **new** pipeline version per
[EXPERIMENT_PROTOCOL_1.5.0.md](EXPERIMENT_PROTOCOL_1.5.0.md).

## Related

- [ZONE_RANKING.md](ZONE_RANKING.md)
- [OOS_VALIDATION_PROTOCOL.md](OOS_VALIDATION_PROTOCOL.md)
- [OOS_DATASET_CONTRACT.md](OOS_DATASET_CONTRACT.md)
- [ANALYTICAL_PARITY.md](ANALYTICAL_PARITY.md)
- [PROJECT_CLOSURE_1.4.0.md](PROJECT_CLOSURE_1.4.0.md)
- [OOS_FAILURE_FORENSICS_1.4.0.md](OOS_FAILURE_FORENSICS_1.4.0.md)
- [EXPERIMENT_PROTOCOL_1.5.0.md](EXPERIMENT_PROTOCOL_1.5.0.md)

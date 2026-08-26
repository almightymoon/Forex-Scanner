# Project Closure — Analytical Pipeline 1.4.0

**Status:** CLOSED (analytical freeze track complete)  
**Pipeline:** `ANALYSIS_PIPELINE_VERSION = 1.4.0`  
**Closed:** 2026-08-26

## What this closure means

The scanner’s **analytical freeze → OOS validation → failure forensics** track for
pipeline **1.4.0** is complete. Product “scanner v1” structure/liquidity/decision
wiring remains as previously delivered; live broker execution remains **Phase 2**
and is out of scope for this closure.

## Delivered

| Deliverable | Location |
|-------------|----------|
| Frozen analytical pipeline 1.4.0 | `services/quant_engine/pipeline/analyze.py` |
| FVG / OB causal lifecycle | `services/quant_engine/fvg/`, `order_blocks/` |
| Zone ranking + HTF trend injection | `services/quant_engine/zones/`, `pipeline/mtf_context.py` |
| Analytical freeze contract | `docs/ANALYTICAL_FREEZE.md` |
| OOS protocol + dataset contract | `docs/OOS_VALIDATION_PROTOCOL.md`, `docs/OOS_DATASET_CONTRACT.md` |
| Locked OOS run + artifacts | `validation/`, `docs/OOS_VALIDATION_REPORT_1.4.0.md` |
| Failure forensics | `docs/OOS_FAILURE_FORENSICS_1.4.0.md`, `validation/forensics_1_4_0.json` |
| Integrity / golden tests | `tests/integrity/`, `tests/fixtures/golden/`, `tests/quant_engine/` |

## OOS outcome (headline)

| Metric | Value |
|--------|-------|
| Dataset | XAUUSD H1 retrospective `xauusd_h1_oos_v1_retrospective_2022_2024` |
| Dataset SHA-256 | `eac96d050a6bacfe879a0506143a053d4ce5ab7304b94cfbab91067211040d73` |
| Trades | 246 |
| Win rate | 38.6% |
| Profit factor | 0.761 |
| Expectancy | −0.091 R |
| Total R | −22.434 |
| Max DD (R) | 30.329 |
| Leakage audit | PASS |
| Reproducibility | PASS |
| **Verdict** | **FAILED OOS VALIDATION** |

## Forensic summary

Primary diagnosis: **directional signal weakness** under frozen ~1.333 R payoff
(observed WR 38.6% &lt; ~42.9% breakeven). Secondary exploratory signals: poor
score/confidence calibration, short-side loss concentration, weak predictive
value of rank/alignment labels. Execution costs are **not** the primary cause
(BASE costs = 0 already negative).

## Explicit non-claims

- 1.4.0 is **not** a proven edge.
- Subgroup forensics are **not** approved filters.
- This closure does **not** authorize silent patches to 1.4.0.

## What remains outside this closure

| Item | Status |
|------|--------|
| Live broker execution | Phase 2 (roadmap) |
| Multi-host validation persistence | Known gap (non-analytical) |
| Prospective post-2026H1 OOS dataset | Not locked; not substituted |
| Versioned optimization (1.5.0+) | Separate experiment — see `EXPERIMENT_PROTOCOL_1.5.0.md` |
| Paper/live shadow of frozen 1.4.0 | Optional ops track; does not change analytics |

## Change control going forward

Any analytical change requires a **new** `ANALYSIS_PIPELINE_VERSION`, golden
fixture updates, integrity suite green, and a new validation report. Do not
amend 1.4.0 behavior in place.

## Related

- [ANALYTICAL_FREEZE.md](ANALYTICAL_FREEZE.md)
- [OOS_VALIDATION_REPORT_1.4.0.md](OOS_VALIDATION_REPORT_1.4.0.md)
- [OOS_FAILURE_FORENSICS_1.4.0.md](OOS_FAILURE_FORENSICS_1.4.0.md)
- [EXPERIMENT_PROTOCOL_1.5.0.md](EXPERIMENT_PROTOCOL_1.5.0.md)

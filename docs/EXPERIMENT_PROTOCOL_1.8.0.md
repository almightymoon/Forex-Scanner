# Experiment Protocol — Pipeline 1.8.0 (Arm H4)

**Status:** COMPLETE — Arm **H4** **PASSED** predeclared success (see caveats in report)  
**Frozen baseline:** 1.4.0  
**Prior:** H1/H2/H3 all FAILED  
**Version:** `1.8.0` emit gates only

Selected policy: `h4_rank1_liquidity_none` (rank-1 primary zone + liquidity_relation NONE).

**Caveat:** TEST trade count is small (n=18). Formal criteria did not require a TEST minimum n; treat as provisional pending more evidence / H5.

## Mechanism

Forensics-compatible labels via re-analysis enrichment:

- `primary_rank` — 1-based rank among same-direction FVG (else OB)
- `liquidity_relation` — from primary zone_context

TEST joins `validation/forensics_enrichment_cache.json` (immutable 1.4.0 enrichment).

## Selection / success

Same floors as H1–H3.

## Runner

```bash
python scripts/run_oos_experiment_1_8_0.py --all
```

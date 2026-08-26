# FVG / Order Block — Limitations (historical)

**Superseded for last-N truncation by lifecycle v1** — see [FVG_OB_LIFECYCLE.md](FVG_OB_LIFECYCLE.md).  
**Ranking** — see [ZONE_RANKING.md](ZONE_RANKING.md) (pipeline **1.3.0**).

## What changed

| Before (≤1.1.0) | After (1.2.0+) |
|-----------------|----------------|
| `SMCEngine._detect_fvg` / `_detect_order_blocks` returned `patterns[-3:]` | Canonical zone sets retain all zones |
| No stable zone status | Explicit ACTIVE / PARTIAL|TOUCHED / MITIGATED |
| Older zones dropped by recency only | Ranking selects patterns for DE; zones uncapped |

## Remaining limitations

- No `INVALIDATED` / `EXPIRED` states (no defensible rule yet beyond mitigation).
- Pattern emit for DecisionEngine soft-capped at 8 after ranking — not detector deletion.
- Creation rules unchanged (not retuned).
- Ranking trend label defaults to structure external bias (HTF mtf optional future inject).

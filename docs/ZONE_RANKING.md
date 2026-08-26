# Zone Ranking + Explainability v1

**Pipeline:** `ANALYSIS_PIPELINE_VERSION = 1.4.0`  
**Ranking module:** `ZONE_RANKING_VERSION = 1.0.0`  
**Code:** `services/quant_engine/zones/{context,ranking}.py`

Ranking is a **consumer** of canonical facts. It does not detect FVG, OB, liquidity, structure, or trend.

---

## Audit (pre-1.3.0 / shallow ranking)

| Item | Behavior |
|------|----------|
| Fields | lifecycle status, absolute mid-price distance, `-created_index` |
| Order | status → distance → newer first |
| Tie-break | zone creation recency only |
| Soft cap | 8 patterns after sort |
| Stable | yes for same price + zones |
| Lookahead | no (price was as-of close) |
| Context | none (no structure/liquidity/trend metadata) |

---

## Architecture

```text
FVGZoneSet / OrderBlockZoneSet   (complete, uncapped)
StructureSnapshot
LiquiditySnapshot
as-of close + as-of ATR
        │
        ▼
build_zone_context() per zone
        │
        ▼
enrich_and_rank_zones()  — lexicographic sort
        │
        ▼
patterns_from_*_zones(..., limit=8)  — soft cap AFTER ranking
        │
        ▼
SMCPattern.metadata: rank, zone_context, rank_reasons
```

---

## Context fields

| Field | Definition | Causal source |
|-------|------------|---------------|
| `structure_alignment` | Zone direction vs `StructureSnapshot.external_bias` | Structure Engine |
| `trend_alignment` | Zone direction vs **resolved HTF trend** (`select_ranking_htf_trend`) | `resolve_mtf_trends` → nearest higher TF |
| `liquidity_relation` | Relation to pools/sweeps in `LiquiditySnapshot` | Liquidity Engine |
| `distance_to_price` | Absolute distance from reference close to zone; **0 if inside** | as-of close |
| `distance_atr` | `distance_to_price / atr` when `atr > 0`, else absolute | as-of ATR |
| `price_inside_zone` | `lo ≤ price ≤ hi` | as-of close |
| `freshness_bars` | `as_of_index - created_index` | zone + as-of |
| `mitigation_state` | Zone lifecycle status string | zone lifecycle |
| `timeframe` | Zone timeframe label | zone |
| `reasons` | Structured explanation tokens | derived |

### Trend source (1.4.0)

1. Pipeline calls `resolve_mtf_trends` (causal HTF; provider preferred, rollup fill).
2. `select_ranking_htf_trend(mtf, primary_tf)` picks the **nearest higher** TF present.
3. That trend is passed into zone context as `trend` (`trend_source=resolved_htf:{TF}`).
4. If no higher-TF trend is available, fallback: `structure_external_bias` (`trend_source=structure_external_bias_fallback`).

Ranking **order** is unchanged; only the trend source is corrected.

Provider vs rollup disagreements remain observational via [HTF_DRIFT.md](HTF_DRIFT.md) — ranking uses the canonical merged HTF context, not a second comparison path.

### Liquidity relation values

| Value | Rule |
|-------|------|
| `ASSOCIATED_SWEEP` | Any `recent_sweeps` level within near-tolerance of zone |
| `NEAR_RELEVANT` | Nearest **ACTIVE** pool near zone, side agrees (BUY↔buy_side, SELL↔sell_side) |
| `OPPOSING` | Nearest ACTIVE pool near zone, side disagrees (BUY↔sell_side, SELL↔buy_side) |
| `NONE` | No near pool/sweep |

Near-tolerance: `max(0.5 * ATR, 0.5 * zone_width, 1e-9)`.

---

## Exact ranking algorithm (lexicographic, lower better)

1. **Lifecycle validity** — ACTIVE=0; PARTIALLY_FILLED/TOUCHED=1; MITIGATED=2
2. **Structure alignment** — ALIGNED=0; NEUTRAL=1; UNDEFINED=2; OPPOSED=3
3. **Liquidity relation** — ASSOCIATED_SWEEP=0; NEAR_RELEVANT=1; NONE=2; OPPOSING=3
4. **Trend alignment** — same ranks as structure
5. **Distance** — `distance_atr` (or absolute when ATR=0); inside zone → 0
6. **Freshness** — `freshness_bars` ascending (fresher preferred when earlier keys tie)
7. **Stable id** — `zone_id` ascending

Soft cap: emit at most **8** patterns per type **after** this sort. ZoneSets remain complete.

---

## Explanation metadata (on each SMCPattern)

```text
rank: 1
zone_context: { ... ZoneRankContext.to_dict() ... }
rank_reasons: ["ACTIVE", "structure_aligned", "trend_aligned", "liquidity_near_relevant", "price_inside_zone", "freshness_bars=4"]
```

No free-form LLM text — structured tokens only.

---

## Causality

`ranking(prefix_T)` uses only:

- zones as of T
- structure/liquidity snapshots as of T
- close and ATR as of T

Appending T+1…N must not change the T snapshot when re-evaluated with `as_of_index=T` and the T price/ATR/snapshots.

---

## Related

- [FVG_OB_LIFECYCLE.md](FVG_OB_LIFECYCLE.md)
- [ANALYTICAL_PARITY.md](ANALYTICAL_PARITY.md)
- [CURRENT_ARCHITECTURE.md](CURRENT_ARCHITECTURE.md)

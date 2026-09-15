# H4 Paper Shadow Monitor

**Status:** ops track (not a new analytical version)  
**Policy:** `h4_rank1_liquidity_none` (provisional pass from 1.8.0)  
**Live default:** unchanged frozen **1.4.0** (ungated)

## Purpose

Accumulate side-by-side paper metrics:

| Stream | Meaning |
|--------|---------|
| `baseline_1_4_0` | Every min-score signal as today |
| `h4_rank1_liquidity_none` | Same signals after H4 emit gate |

Does **not** write into live scanner config unless you explicitly set
`SCANNER_EMIT_POLICY` after review.

## Run

```bash
# Recent chart CSV (fast)
python scripts/paper_shadow_h4.py \
  --csv chart_csv/FXNavigators_XAUUSD_H1.csv \
  --tail 800

# Locked retrospective window (slower, comparable cadence)
python scripts/paper_shadow_h4.py \
  --csv benchmarks/data/retrospective/XAUUSD/H1_2022_2024_v1/XAUUSD_H1_2022_2024.real.csv.gz \
  --start 2024-06-01 --end 2024-07-11
```

## Artifacts

`benchmarks/live/h4_paper_shadow/`

- `events.jsonl` — append-only baseline + gated events
- `latest_summary.json` — last run metrics
- `summary_<utc>.json` — per-run snapshot

## Promotion rule

Only set live opt-in after several paper runs show stable gated expectancy ≥ 0
with enough trades (prefer n≥30) and product review:

```bash
# .env — paper/live opt-in ONLY after review
SCANNER_EMIT_POLICY=h4_rank1_liquidity_none
```

Unset / empty = frozen ungated 1.4.0.

## Accumulated paper runs

### 2026-09-15 — chart tail 800

| Stream | n | WR | PF | exp | total R |
|--------|---|----|----|-----|---------|
| Baseline | 12 | 50.0% | 1.56 | +0.255 | +3.06 |
| H4 gated | 2 | 0% | 0 | −1.0 | −2.0 |
| Suppressed | 105 | | | | |

### 2026-09-15 — locked TEST window 2024-01-01 → 2024-07-11

| Stream | n | WR | PF | exp | total R |
|--------|---|----|----|-----|---------|
| Baseline | 67 | 53.7% | 1.44 | +0.212 | +14.23 |
| H4 gated | **6** | 33.3% | 0.80 | **−0.222** | −1.33 |
| Suppressed | 669 | | | | |

**Verdict so far:** Do **not** enable `SCANNER_EMIT_POLICY`. Gated trade count stays far below the ~30 target and expectancy is negative on this paper cadence.

Note: paper streams use **independent cooldowns**, so baseline n here (67) is not the same as locked OOS n=246 (shared cooldown on ungated emit). Compare streams within each paper run; use OOS report for the locked filter-on-corpus result (n=18).

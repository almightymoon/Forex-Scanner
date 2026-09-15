# Analytics Experiment Scoreboard

Living summary of versioned experiments after analytical freeze of **1.4.0**.

| Version | Arm | Hypothesis | VAL qualified? | TEST verdict | Report |
|---------|-----|------------|----------------|--------------|--------|
| 1.4.0 | baseline | Frozen pipeline OOS | n/a | **FAILED OOS** | [OOS_VALIDATION_REPORT_1.4.0.md](OOS_VALIDATION_REPORT_1.4.0.md) |
| 1.5.0 | H1 | Score/confidence emit bands | No | **FAILED** | [EXPERIMENT_REPORT_1.5.0.md](EXPERIMENT_REPORT_1.5.0.md) |
| 1.6.0 | H3 | Direction / structure / HTF gates | No | **FAILED** | [EXPERIMENT_REPORT_1.6.0.md](EXPERIMENT_REPORT_1.6.0.md) |
| 1.7.0 | H2 | TP remap / payoff geometry | No | **FAILED** | [EXPERIMENT_REPORT_1.7.0.md](EXPERIMENT_REPORT_1.7.0.md) |
| 1.8.0 | H4 | Zone rank / liquidity gates | **Yes** (`h4_rank1_liquidity_none`) | **PASSED*** | [EXPERIMENT_REPORT_1.8.0.md](EXPERIMENT_REPORT_1.8.0.md) |
| H5 | shadow | Prospective post-2026H1 on frozen 1.4.0 | — | **BLOCKED** (accrual) | [EXPERIMENT_PROTOCOL_H5.md](EXPERIMENT_PROTOCOL_H5.md) |

\*H4 TEST n=18 (small). Paper shadow on 2024 window: gated n=6, exp −0.222 — **do not promote** yet. See [H4_PAPER_SHADOW.md](H4_PAPER_SHADOW.md).

## Rules (unchanged)

- Do not patch 1.4.0 in place.
- One arm per version; no silent factorial dumps.
- Select on VALIDATION only; TEST once after lock.
- Live default remains `ANALYSIS_PIPELINE_VERSION = 1.4.0` until a version **passes** and is explicitly promoted.

## Product path while analytics are mixed

1. Validation outcome DB store (done).
2. Dashboard filters — score + direction + timeframe (done).
3. Health exposes `validation_store` + `pipeline_version` (done).
4. Opt-in paper shadow: `SCANNER_EMIT_POLICY=h4_rank1_liquidity_none` (default off).
   Runner: `scripts/paper_shadow_h4.py` — see [H4_PAPER_SHADOW.md](H4_PAPER_SHADOW.md).
5. Live broker execution remains Phase 2.
6. H5 when post-2026H1 accrual completes (≥1400 bars through 2026-09-30).

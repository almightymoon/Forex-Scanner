# XAUUSD H1 post-2026H1 locked benchmark protocol

This protocol was frozen before completion of candle accrual, window
selection, labeling, or engine evaluation.

## Candidate

- Candidate: `v2.3.0-rc1`
- Frozen code commit: `3fd5d7c74b82c3728d7badaa6cd72044bdd6bd1d`
- Baseline: `v2.2.0`

## Accrual gate

Benchmark construction cannot begin until both conditions hold:

1. Coverage reaches at least `2026-09-30T20:00:00Z`.
2. At least 1,400 unique normalized XAUUSD H1 bars exist.

During accrual:

- No swing-engine version may run on the candles.
- No labels may be created.
- Existing immutable tranches may not be overwritten.
- Every new export must become a separately checksummed tranche.

## Deterministic window selection

After the accrual gate passes:

1. Combine immutable tranches and normalize timestamps to UTC.
2. Deduplicate timestamps and fail on conflicting OHLC values.
3. Exclude the first and last 48 bars as guards.
4. Divide the remaining ordered rows into six equal chronological buckets.
5. Select the centered contiguous 192-bar window from each bucket.
6. Fail rather than alter the protocol if six non-overlapping windows cannot
   be produced.

Window selection may not use labels, predictions, engine output, or realized
benchmark performance.

## Labeling

- Predictions and engine versions remain hidden.
- Two labeling passes are required, separated by at least three days.
- Conflicts require explicit adjudication.
- Window bars and labels are checksummed and frozen before evaluation.

## Evaluation

The candidate and baseline each receive one evaluation. No error analysis or
tuning is allowed before the release decision.

Promotion requires:

- Zero prefix-stability failures.
- Location precision at least 0.80.
- Location recall at least 0.70.
- Location F1 at least 0.75.
- Semantic F1 at least 0.60.
- Major External precision at least 0.85.
- Major External recall at least 0.40.
- Worst-window location F1 at least 0.50.
- No aggregate location-F1 or semantic-F1 regression versus v2.2.

The machine-readable source of truth is:

`benchmarks/protocols/XAUUSD_H1_post_2026H1_locked_protocol.json`

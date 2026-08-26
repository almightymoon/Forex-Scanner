# Validation Persistence — Current Limitations (audit only)

**Not migrated in this task.** Implementation: `services/validation_engine/storage.py` `OutcomeStore`.

## Current design

- File-backed JSON: default `data/validation_outcomes.json`
- In-memory dict + full-file rewrite on each `save` / `update`
- Wired when live signals exceed `min_alert_score` (`SignalBuilder`)

## Limitations

| Concern | Impact |
|---------|--------|
| Concurrency | Two processes can interleave read/modify/write → lost updates |
| Multi-host | Local filesystem is not shared across API replicas |
| Multi-process | Same host, multiple workers → race on the JSON file |
| Reproducibility | Outcomes depend on which host/process handled the scan |
| Durability | No transaction / fsync guarantees beyond OS write |

## Correctness note

No silent outcome-corruption bug was found beyond these architectural limits. SL/TP evaluation uses the same **SL-first** ambiguous-bar policy as backtest execution.

## Follow-up recommendation

Swap `OutcomeStore` for Postgres (schema already foreshadowed in comments) with idempotent signal IDs — without changing validation metrics formulas.

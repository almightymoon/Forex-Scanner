# Validation Persistence

**Implementation:** `services/validation_engine/storage.py`

## Backends

| Backend | When used | Notes |
|---------|-----------|-------|
| `DbOutcomeStore` | Default via `get_outcome_store()` | SQLite or PostgreSQL through `shared.db_factory.get_database()` |
| `FileOutcomeStore` | Explicit `path=` (tests) or DB init failure | Atomic write (`tempfile` + `os.replace`) |

Idempotent upserts key on signal `id` (full UUID hex from `new_signal_id()`).
SL/TP evaluation policy is unchanged (ambiguous bar → SL first).

## Schema

- Migration: `database/migrations/004_validation_outcomes.sql`
- Also created in adapter `_init_schema` for Postgres/SQLite auto-bootstrap
- Table: `validation_outcomes`

## Limitations (remaining)

| Concern | Status |
|---------|--------|
| Multi-host | **Resolved** when `USE_POSTGRES=true` / shared Postgres |
| Multi-process (same host, SQLite) | Better than JSON; still prefer Postgres for replicas |
| File fallback | Single-host only; atomic rewrite only |
| Legacy JSON import | Not auto-migrated — re-register from live scans or ETL if needed |

## Usage

```python
from services.validation_engine import SignalValidator, get_outcome_store

validator = SignalValidator()  # DB-backed by default
# tests:
validator = SignalValidator(store=get_outcome_store(path="/tmp/outcomes.json"))
```

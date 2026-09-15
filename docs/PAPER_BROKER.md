# Paper Broker (Phase 2 prep)

**Status:** available, **opt-in**  
**Does not** enable `SCANNER_EMIT_POLICY`  
**Does not** modify frozen analytical pipeline **1.4.0**

Paper fills sit between alert-only live scanning and real venue APIs (`OANDA` / `MT5` remain disabled).

## What it is

| Piece | Path |
|-------|------|
| Service | `services/broker_service/paper.py` |
| Live hook | `SignalBuilder._maybe_paper_trade` when `PAPER_BROKER_ENABLED=true` |
| Offline twin | `scripts/paper_broker_1_4_0.py` |
| Artifacts | `benchmarks/live/paper_broker/` |

Fills use `simulate_trade` with OOS-parity `ExecutionConfig("signal_close", "sl_first", 0, 0, 0)`.

## Enable live journaling

```bash
# .env — local ops (do not commit secrets)
PAPER_BROKER_ENABLED=true
# Leave SCANNER_EMIT_POLICY unset / empty
```

On each alert-score signal the scanner journals an open paper order and settles against subsequent candles.

Status:

```bash
PYTHONPATH=. python scripts/paper_broker_status.py
```

Artifacts land under `benchmarks/live/paper_broker/` (gitignored).

## Offline smoke

```bash
PYTHONPATH=. python scripts/paper_broker_1_4_0.py \
  --csv benchmarks/data/retrospective/XAUUSD/H1_2022_2024_v1/XAUUSD_H1_2022_2024.real.csv.gz \
  --start 2024-07-01 --end 2024-07-11
```

## Distinction

| Track | Purpose |
|-------|---------|
| Paper broker | Phase-2-prep fills for **ungated 1.4.0** |
| H4 paper shadow | Compare baseline vs provisional emit gate — [H4_PAPER_SHADOW.md](H4_PAPER_SHADOW.md) |
| H5 | Prospective shadow when post-2026H1 accrual clears — [EXPERIMENT_PROTOCOL_H5.md](EXPERIMENT_PROTOCOL_H5.md) |
| Live broker APIs | Still later Phase 2 (venue orders) |

## Non-goals

- No live order routing
- No H4 gate promotion
- No DecisionEngine / zone / ranking changes

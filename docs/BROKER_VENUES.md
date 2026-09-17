# Live Broker Venues (Phase 2)

**Status:** stubs only — **orders refused by default**  
**OANDA is optional** — leave `BROKER_VENUE=none` if you have no account.  
Paper trading uses [PAPER_BROKER.md](PAPER_BROKER.md) + market-data OHLC only.

```
Scanner signals
    ├── PaperBroker          ← PAPER_BROKER_ENABLED (simulated fills; no venue)
    └── BrokerVenue (stub)   ← optional; BROKER_VENUE + BROKER_VENUE_ORDERS_ENABLED
            ├── none (default)
            ├── oanda (optional)
            └── mt5 (optional)
```

## Safety switches

| Env | Default | Meaning |
|-----|---------|---------|
| `BROKER_VENUE` | `none` | Which stub to load (`none` / `oanda` / `mt5`) |
| `BROKER_VENUE_ORDERS_ENABLED` | off | Second switch — must be on to even attempt a venue order |
| `OANDA_API_KEY` / `OANDA_ACCOUNT_ID` | empty | Only if using OANDA |
| `OANDA_ENV` | `practice` | `practice` or `live` host |
| `MT5_ENABLED` | false | Local MT5 bridge flag (Windows) |

Skip the OANDA arming steps entirely when `BROKER_VENUE=none`. Paper settle:
`PYTHONPATH=. python scripts/paper_broker_settle.py`.

## Code

| Path | Role |
|------|------|
| `services/broker_service/venue.py` | `BrokerVenue`, `VenueOrderRequest/Result` |
| `services/broker_service/oanda_venue.py` | OANDA stub |
| `services/broker_service/mt5_venue.py` | MT5 stub |
| `services/broker_service/factory.py` | `get_broker_venue()` / `venue_status()` |

Market-data OHLC adapters remain under `services/market_data_service/providers/disabled/` and stay **out** of the active failover chain.

## Arming practice (manual)

1. Put practice `OANDA_API_KEY` + `OANDA_ACCOUNT_ID` in `.env`
2. `BROKER_VENUE=oanda` and `OANDA_ENV=practice`
3. Check: `PYTHONPATH=. python scripts/oanda_practice_smoke.py`
4. Only then set `BROKER_VENUE_ORDERS_ENABLED=true`
5. Optional probe: `PYTHONPATH=. python scripts/oanda_practice_smoke.py --arm-check`

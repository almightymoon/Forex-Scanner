# Live Broker Venues (Phase 2)

**Status:** stubs only — **orders refused by default**  
**Separate from** market data (Twelve Data / Polygon) and from [PAPER_BROKER.md](PAPER_BROKER.md)

```
Scanner signals
    ├── PaperBroker          ← PAPER_BROKER_ENABLED (simulated fills)
    └── BrokerVenue (stub)   ← BROKER_VENUE + BROKER_VENUE_ORDERS_ENABLED
            ├── oanda
            └── mt5
```

## Safety switches

| Env | Default | Meaning |
|-----|---------|---------|
| `BROKER_VENUE` | `none` | Which stub to load (`oanda` / `mt5` / `none`) |
| `BROKER_VENUE_ORDERS_ENABLED` | off | Second switch — must be on to even attempt a venue order |
| `OANDA_API_KEY` / `OANDA_ACCOUNT_ID` | empty | Credentials for OANDA practice/live |
| `OANDA_ENV` | `practice` | `practice` or `live` host |
| `MT5_ENABLED` | false | Local MT5 bridge flag (Windows) |

Even when both switches are on, OANDA will POST a MARKET order to the practice
(or live) host. Keep `BROKER_VENUE_ORDERS_ENABLED=false` until practice keys are
configured and you intentionally want fills.

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

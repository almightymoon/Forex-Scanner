# Disabled Providers (Phase 2 — Broker Layer)

These implementations are **not active** in the scanner. They are kept so broker
integration can be restored without rewriting adapters.

## Phase 1 (current)

Market data only:

```
Twelve Data → Polygon → Simulated (dev only)
```

## Phase 2 (future)

When automated trading is supported, introduce a separate **Broker Layer**:

```
Scanner → Signals → Broker Interface
                      ├── OANDA
                      ├── MetaTrader 5
                      ├── cTrader
                      ├── Interactive Brokers
                      └── …
```

Broker providers must **not** be mixed into the market-data failover chain.
OHLC and live quotes stay on Twelve Data / Polygon; execution goes through brokers.

## Files

| File | Purpose |
|------|---------|
| `oanda_provider.py` | OANDA v20 REST — historical OHLC + pricing (broker) |
| `mt5_provider.py` | MetaTrader 5 bridge stub (broker) |

## Restoring OANDA (market data — not recommended)

1. Move the provider back under `services/market_data_service/`
2. Register in `factory.ACTIVE_PROVIDERS`
3. Add API keys to `.env`
4. Re-enable in `config/market.yaml` only if you explicitly want it as OHLC source

For trading, prefer wiring OANDA through a future `services/broker_service/` instead.

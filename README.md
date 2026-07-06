# FX Navigators Scanner (Project Atlas)

Institutional-quality forex scanner with transparent AI-assisted scoring, Smart Money Concepts, and multi-timeframe confirmation.

## Quick Start

```bash
# Install Python deps
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r apps/api/requirements.txt

# Run tests
./scripts/test.sh

# API server
./scripts/run-api.sh

# Web dashboard
cd apps/web && npm install && npm run dev

# Database (PostgreSQL + TimescaleDB — optional)
docker compose up -d
```

- API: http://localhost:8001
- API Docs: http://localhost:8001/docs
- Dashboard: http://localhost:3000

## Project Structure

```
scanner/
├── apps/
│   ├── web/                 # Next.js dashboard
│   └── api/                 # FastAPI gateway
├── services/
│   ├── quant_engine/        # Core IP — scoring & SMC algorithms
│   │   ├── swing/
│   │   ├── market_structure/
│   │   ├── liquidity/
│   │   ├── order_blocks/
│   │   ├── fvg/
│   │   ├── trend/
│   │   ├── confidence/
│   │   ├── decision/        # Orchestrator + momentum/volatility/risk/news/mtf
│   │   ├── features/        # Normalized feature extraction
│   │   ├── detection/       # SMC pattern detection
│   │   └── indicators/      # EMA, ADX, VWAP, etc.
│   ├── data_collector/      # Market data ingestion (single source of truth)
│   ├── scanner_service/     # Pipeline, data loading, signal assembly
│   ├── market_data_service/
│   ├── news_service/
│   └── notification_service/
├── shared/
│   ├── types/
│   └── config/
├── config/
│   └── scoring.yaml         # V2 engine weights
├── database/
└── docs/
```

**`quant_engine/`** is the heart of the platform — swing analysis, structure, liquidity, order blocks, FVGs, trend, confidence aggregation, and the decision orchestrator. Supporting services (data collection, APIs, dashboard, billing) exist to feed and deliver it.

Legacy import paths (`services.scanner_service.*`, `services.smc_service.*`, etc.) remain as thin shims re-exporting from `quant_engine`.

## Market Data (Phase 1)

Provider priority:

1. **Twelve Data** — primary OHLC and live quotes
2. **Polygon** — failover when `fallback_enabled: true` in `config/market.yaml`
3. **Simulated** — development only (`ENABLE_SIMULATED_DATA=true`)

Configure in `.env`:

```bash
TWELVE_DATA_API_KEY=your_key
POLYGON_API_KEY=your_key
ENABLE_SIMULATED_DATA=false   # explicit opt-in for dev
```

Broker integrations (OANDA, MT5, etc.) are **Phase 2** and live under
`services/market_data_service/providers/disabled/` until a separate broker layer is introduced.

## Core Features (MVP)

- **Decision Engine** — 100-point transparent scoring across 7 categories
- **28 forex pairs** + **Gold (XAU/USD)** + Silver (XAG/USD) with live Swissquote prices
- **Multi-timeframe** — M1 through D1
- **Backtesting** — walk-forward win rate, R:R, drawdown per pair
- **AI Explanations** — OpenAI-powered (template fallback)
- **PostgreSQL** — auto-detect with SQLite fallback (`USE_POSTGRES=true`)
- **SMC** — BOS, CHoCH, Order Blocks, FVG, Liquidity Sweeps
- **News filter** — Economic calendar integration
- **Alerts** — Telegram, Discord, Email, Push

## Documentation

- [Milestones](docs/MILESTONES.md) — Full 30-milestone roadmap
- [Architecture](docs/ARCHITECTURE.md) — System design
- [API Specification](docs/API.md) — REST + WebSocket endpoints
- [Decision Engine](docs/DECISION_ENGINE.md) — Scoring logic

## License

Proprietary — FX Navigators

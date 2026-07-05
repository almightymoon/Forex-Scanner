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
fxnavigators/
├── apps/
│   ├── web/                 # Next.js dashboard
│   └── api/                 # FastAPI gateway
├── services/
│   ├── market-data-service/
│   ├── indicator-service/
│   ├── scanner-service/     # Decision engine (core IP)
│   ├── smc-service/
│   ├── news-service/
│   └── notification-service/
├── shared/
│   ├── types/
│   └── configs/
├── database/
│   ├── schema.sql
│   └── seed.sql
├── infrastructure/
│   └── docker/
└── docs/
```

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

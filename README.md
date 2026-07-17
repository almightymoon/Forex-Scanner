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
fx-navigators/
├── swing_engine/            # Single source of truth — swing detection (v2.0.0: production freeze)
├── services/
│   ├── bar_builder/         # Deterministic M1–D1 bar generation
│   ├── data_collector/      # Market data ingestion + raw tick storage
│   ├── quant_engine/        # Consumers (market_structure uses swing_engine)
│   └── scanner_service/     # Pipeline orchestration
├── config/
│   ├── swing_detection.yaml
│   └── data_collector.yaml
├── benchmarks/reports/      # Evaluation JSON/CSV/MD + regression dashboard
├── benchmarks/history/      # Regression history (JSONL, per-run metrics)
├── benchmarks/live/         # Paper-mode swing logs + live validation reports
├── tests/
│   ├── test_swing_engine_pkg/
│   ├── swing_detection/
│   ├── bar_builder/
│   └── integration/
└── docs/SWING_DETECTION.md
```

## Real XAUUSD H1 Benchmark

Synthetic labels are retained only for deterministic software regression. Build
the trader-grade benchmark from an immutable real H1 CSV:

```bash
python scripts/prepare_xauusd_h1_benchmark.py \
  --input /path/to/XAUUSD_H1.csv \
  --source WEALTHTEX_MT5 \
  --source-timezone Europe/Helsinki

python scripts/annotate_swings.py benchmarks/labels/XAUUSD_H1.human.json
python scripts/validate_human_benchmark.py
```

See `docs/XAUUSD_H1_BENCHMARK.md`. MT5 for macOS users can export history with
`tools/mt5/ExportXAUUSDH1Benchmark.mq5`.

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
- [Swing Detection](docs/SWING_DETECTION.md) — engine spec (v2.0.0: human-review benchmarks, score breakdown studio, calibration)
- [XAUUSD H1 Benchmark](docs/XAUUSD_H1_BENCHMARK.md) — real-data prepare/annotate/validate workflow
- [Project Roadmap](docs/ROADMAP.md) — master plan to production (BOS, CHoCH, liquidity, decision engine)

## License

Proprietary — FX Navigators

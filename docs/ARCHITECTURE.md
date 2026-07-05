# FX Navigators Scanner — System Architecture

## Overview

Project Atlas is built as a **modular monorepo** where the Decision Engine is the central analysis layer powering every product surface: scanner, dashboard, alerts, AI explanations, trade journal, and future MT5 plugin.

```
┌─────────────────────────────────────────────────────────────┐
│                     Client Layer                             │
│  Next.js Web  │  Flutter Mobile  │  Admin Portal  │  MT5    │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                   API Gateway (FastAPI)                      │
│  REST /api/v1/*  │  WebSocket /ws/scanner  │  Auth (JWT)     │
└──────────────────────────┬──────────────────────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        ▼                  ▼                  ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ Market Data  │  │   Scanner    │  │ Notification │
│   Service    │  │   Pipeline   │  │   Service    │
└──────┬───────┘  └──────┬───────┘  └──────────────┘
       │                 │
       ▼                 ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│  Indicator   │  │     SMC      │  │    News      │
│   Engine     │  │   Engine     │  │   Service    │
└──────┬───────┘  └──────┬───────┘  └──────┬───────┘
       │                 │                  │
       └────────┬────────┴──────────────────┘
                ▼
       ┌─────────────────┐
       │ Decision Engine  │  ← Core IP (100-point scoring)
       └────────┬────────┘
                ▼
       ┌─────────────────┐
       │  PostgreSQL +    │
       │  TimescaleDB     │
       └─────────────────┘
```

## Scanner Pipeline

```
Live Market Data
        │
        ▼
Market Data Service ──→ Validate & store candles
        │
        ▼
Indicator Engine ──→ EMA, RSI, MACD, ATR, ADX, VWAP, BB
        │
        ▼
SMC Engine ──→ BOS, CHoCH, Order Blocks, FVG, Liquidity Sweeps
        │
        ▼
Decision Engine ──→ 7-category scoring → Signal
        │
        ├──→ AI Explanation (template → LLM)
        ├──→ Database (scanner_results)
        ├──→ Notifications (Telegram, Discord, Email)
        └──→ Dashboard (WebSocket push)
```

## Technology Stack

| Layer | Technology |
|-------|-----------|
| API Gateway | FastAPI + Uvicorn |
| Database | PostgreSQL 16 + TimescaleDB |
| Cache | Redis 7 |
| Web Frontend | Next.js 15 + React 19 |
| Mobile (planned) | Flutter |
| Auth | JWT (python-jose) |
| Market Data | OANDA / Twelve Data (production) |
| AI | OpenAI / Claude (explanations only) |
| Infrastructure | Docker Compose → Kubernetes |

## Data Flow

1. **Market Data Service** ingests ticks/candles from provider
2. Candles stored in TimescaleDB hypertable (`candles`)
3. **Indicator Engine** computes technical indicators per symbol/timeframe
4. **SMC Engine** detects institutional patterns on OHLC data
5. **Scanner Pipeline** orchestrates multi-timeframe analysis
6. **Decision Engine** scores each setup 0–100 with transparent breakdown
7. Signals above threshold saved and pushed to clients

## Security Model

- JWT authentication for API access
- Role-based access: Guest, Free, Pro, Elite, Admin
- API keys for programmatic access (Enterprise)
- Rate limiting per plan tier
- Audit logging for admin actions

## Scalability

Each service can scale independently:
- Market Data: horizontal scaling with symbol sharding
- Scanner: parallel symbol scanning via asyncio
- API: multiple Uvicorn workers behind load balancer
- Database: TimescaleDB compression + retention policies

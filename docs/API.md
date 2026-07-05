# FX Navigators Scanner API (v1)

Base URL: `http://localhost:8000`

Interactive docs: `http://localhost:8000/docs`

## Authentication

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/auth/register` | Register new user |
| POST | `/api/v1/auth/login` | Login, returns JWT token |

## Market Data

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/symbols` | List all tradeable symbols |
| GET | `/api/v1/market/{symbol}/candles` | OHLCV candles for a symbol |

Query params for candles:
- `timeframe` — M1, M5, M15, M30, H1, H4, D1 (default: H1)
- `count` — number of candles (default: 200, max: 1000)

## Scanner

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/scanner/live` | Live scanner feed (all pairs) |
| GET | `/api/v1/scanner/{symbol}` | Detailed scan for one symbol |
| WS | `/ws/scanner` | Real-time scanner updates (30s interval) |

Query params for live scanner:
- `min_score` — minimum confidence score (default: 60)
- `timeframe` — analysis timeframe (default: H1)
- `limit` — max results (default: 20)

### Scanner Response Example

```json
{
  "symbol": "EURUSD",
  "timeframe": "H1",
  "direction": "buy",
  "score": 88,
  "rating": "strong",
  "trend": "bullish",
  "risk_level": "low",
  "score_breakdown": {
    "trend": 18,
    "smc": 22,
    "momentum": 12,
    "support_resistance": 8,
    "volume_volatility": 9,
    "mtf_alignment": 10,
    "news_risk": 10
  },
  "technical_reasons": ["EMA 20 > 50 > 200 aligned bullish", "ADX strong at 32.1"],
  "smc_reasons": ["Liquidity Sweep detected (buy)", "Order Block detected (buy)"],
  "entry_zone_low": 1.0865,
  "entry_zone_high": 1.0878,
  "stop_loss": 1.0842,
  "take_profit_1": 1.0910,
  "risk_reward": 1.33,
  "ai_explanation": "EURUSD — BUY — 88/100\n\nTrend: EMA 20 > 50 > 200 aligned bullish\n..."
}
```

## Alerts

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/alerts` | List user alerts |
| POST | `/api/v1/alerts` | Create alert rule |
| DELETE | `/api/v1/alerts/{id}` | Delete alert |

## Watchlist

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/watchlist` | Get watchlist |
| POST | `/api/v1/watchlist` | Update watchlist symbols |

## Economic Calendar

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/calendar` | Upcoming economic events |

## Health

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Service health check |

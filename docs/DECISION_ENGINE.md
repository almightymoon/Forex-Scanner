# FX Navigators Decision Engine (v1)

## Philosophy

The scanner never generates a Buy or Sell because one indicator crossed another. It answers:

> "Is this setup objectively good enough to risk money on?"

Every setup starts at **0 points** and earns points as evidence accumulates.

## Score Categories (100 Points Total)

| Category | Weight | What It Measures |
|----------|--------|-----------------|
| Market Trend | 20 | EMA alignment, ADX, HH/HL, VWAP |
| Smart Money Concepts | 25 | BOS, CHoCH, OB, FVG, Liquidity Sweeps |
| Momentum | 15 | RSI zone, MACD histogram, ATR expansion |
| Support/Resistance | 10 | S/R proximity, Fibonacci, pivot confirmation |
| Volume & Volatility | 10 | Volume vs average, ATR, breakout strength, spread |
| Multi-Timeframe | 10 | M15, H1, H4, D1 trend alignment |
| News Risk | 10 | High-impact events in next 30–120 minutes |

## Scoring Details

### Trend (max 20)

| Condition | Points |
|-----------|--------|
| EMA 20 > 50 > 200 (or bearish inverse) | +8 |
| ADX > 25 | +5 |
| Higher highs detected | +3 |
| Higher lows detected | +2 |
| Price above VWAP | +2 |

### SMC (max 25)

| Pattern | Points |
|---------|--------|
| Order Block | +7 |
| Liquidity Sweep | +6 |
| Break of Structure | +5 |
| Breaker Block | +5 |
| Fair Value Gap | +4 |
| CHoCH | +3 |
| Equal Highs/Lows | +3 |

### Momentum (max 15)

| Condition | Points |
|-----------|--------|
| MACD histogram aligned with trend | +5 |
| RSI in optimal zone (50–70 bullish, 30–50 bearish) | +5 |
| ATR indicating volatility expansion | +5 |

### News Risk (max 10)

| Condition | Points |
|-----------|--------|
| High-impact news within 30 min | 0 |
| High-impact news within 2 hours | 3 |
| Medium-impact news | 5 |
| No major news | 10 |

## Confidence Levels

| Score | Rating | Action |
|-------|--------|--------|
| 90–100 | Elite Setup | Alert immediately |
| 80–89 | Strong | Alert (default threshold) |
| 70–79 | Good | Display, no alert |
| 60–69 | Moderate | Display only |
| Below 60 | Ignore | Hidden |

## Risk Grading

- **Low**: Score ≥ 85, no imminent news, normal spread
- **Medium**: Score 70–84
- **High**: Score < 70, elevated spread, or news within 15 min
- **Extreme**: Reserved for conflicting signals

## Trade Levels

Calculated using ATR-based positioning:

- **Entry zone**: Current price ± 0.1–0.2 ATR
- **Stop loss**: 1.5 ATR from entry
- **TP1**: 2 ATR (R:R ~1.3)
- **TP2**: 3 ATR (R:R ~2.0)
- **TP3**: 5 ATR (R:R ~3.3)

## Implementation

Core logic lives in `services/scanner_service/engine.py`:

```python
engine = DecisionEngine()
signal = engine.evaluate(
    symbol="EURUSD",
    timeframe=Timeframe.H1,
    candles=candles,
    indicators=indicators,
    smc_patterns=smc_patterns,
    mtf_trends={"M15": TrendDirection.BULLISH, "H4": TrendDirection.BULLISH},
    news=news_context,
)
# signal.score → 88
# signal.score_breakdown → {trend: 18, smc: 22, momentum: 12, ...}
```

## Four Questions Answered

1. **Should I trade this?** → Score + rating + risk level
2. **Why is it a good setup?** → Technical + SMC reasons + score breakdown
3. **How risky is it?** → Risk grading + news filter + spread check
4. **How has this performed?** → Backtesting engine (Milestone 12)

# Backtest Execution Rules

Source of truth: `services/backtesting_service/execution.py`  
Consumed by: `services/backtesting_service/backtester.py`

## Entry

- **Mode:** `signal_close`
- Fill price = close of the signal bar (`candles[i].close`)
- Optional costs worsen the fill:
  - Buy: `entry + half_spread + slippage`
  - Sell: `entry - half_spread - slippage`
- Commission is subtracted from PnL in price units (`commission_pips * pip_size`)

Defaults: all costs `0.0` (research mode without broker model).

## Stop loss / take profit

- Evaluated only on **subsequent** bars: `candles[i+1 : i+1+forward_bars]`
- Uses `signal.stop_loss` and `signal.take_profit_1` only
- Long: SL if `low <= sl`; TP if `high >= tp`
- Short: SL if `high >= sl`; TP if `low <= tp`

## Ambiguous candle

If one bar’s range touches **both** SL and TP:

```text
ambiguous_policy = "sl_first"  # ONLY supported policy
→ outcome = loss at stop_loss
→ trade.ambiguous = True
```

We **never** choose the favourable outcome. No intrabar path is assumed.

## Timeout

If neither SL nor TP hits within `forward_bars`:

- Exit at last forward bar’s close
- Classify win/loss/breakeven by mark-to-market PnL sign

## Metrics (verified)

| Metric | Formula |
|--------|---------|
| Win rate | `wins / total_trades * 100` |
| Profit factor | `sum(positive pnl_price) / abs(sum(negative pnl_price))` (`None` if no losses) |
| Expectancy / avg R | `mean(pnl_price / initial_risk)` |
| Max drawdown (pips) | Peak-to-trough of cumulative pip equity |
| Max drawdown (R) | Peak-to-trough of cumulative R |

Unit tests with hand-calculated values live in
`tests/integrity/test_pipeline_integrity.py`.

## Walk-forward chronology

`BacktestEngine.run` walks `i` ascending with expanding `candles[:i+1]` and a
cooldown after each trade. **No time shuffling.**

This is expanding-window evaluation, not nested train/validation parameter
optimization. Chronological year splits for swing research remain in
`swing_engine/dataset_splits.py`.

## News limitation

Historical backtests inject a **neutral** `NewsContext` unless the caller
provides a calendar that is known to be available as-of each bar. Final revised
economic calendars can leak information that was not available historically —
results must not be presented as perfectly causal for news.

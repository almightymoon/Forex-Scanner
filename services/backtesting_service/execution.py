"""Backtest trade execution simulator — documented deterministic rules.

Analytical signals come from the canonical pipeline. This module only
simulates fills and aggregates performance metrics.

## Entry
``entry_mode="signal_close"`` — enter at the signal bar's close (window[-1].close).
Spread (if configured) worsens the fill: buy pays +half_spread, sell receives −half_spread.

## SL / TP
Checked on subsequent bars only (``candles[i+1:]``), never on the signal bar.

## Ambiguous candle
If the same bar's range touches both SL and TP:
``ambiguous_policy="sl_first"`` (default) — treat as **stop loss**.
This is intentionally conservative; we never pick the favorable outcome.
No intrabar path data is assumed.

## Costs
``spread_pips``, ``slippage_pips``, ``commission_pips`` are converted via ``pip_size``
and applied to entry (spread+slippage) and optionally as a flat commission debit
in pips on the trade PnL.

## Metrics
- win_rate = wins / total_trades * 100
- profit_factor = gross_profit / gross_loss (None if no losses)
- expectancy = mean(R) where R = pnl_price / initial_risk
- avg_r = same as expectancy (mean R-multiple)
- max_drawdown = peak-to-trough of cumulative R (or pip equity when risk unknown)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


AmbiguousPolicy = Literal["sl_first"]
EntryMode = Literal["signal_close"]


@dataclass(frozen=True)
class ExecutionConfig:
    entry_mode: EntryMode = "signal_close"
    ambiguous_policy: AmbiguousPolicy = "sl_first"
    spread_pips: float = 0.0
    slippage_pips: float = 0.0
    commission_pips: float = 0.0


@dataclass
class SimulatedTrade:
    entry_price: float
    exit_price: float
    direction: str
    outcome: str  # win | loss | breakeven
    pnl_pips: float
    pnl_price: float
    risk_price: float
    r_multiple: float
    score: int
    ambiguous: bool = False
    bars_held: int = 0


@dataclass
class PerformanceMetrics:
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    breakeven: int = 0
    win_rate: float = 0.0
    profit_factor: float | None = None
    expectancy: float = 0.0
    avg_r: float = 0.0
    max_drawdown_r: float = 0.0
    max_drawdown_pips: float = 0.0
    avg_winner_pips: float = 0.0
    avg_loser_pips: float = 0.0
    consecutive_wins_max: int = 0
    consecutive_losses_max: int = 0
    avg_score: float = 0.0

    def to_dict(self) -> dict:
        return {
            "total_trades": self.total_trades,
            "wins": self.wins,
            "losses": self.losses,
            "breakeven": self.breakeven,
            "win_rate": round(self.win_rate, 1),
            "profit_factor": (
                round(self.profit_factor, 3) if self.profit_factor is not None else None
            ),
            "expectancy": round(self.expectancy, 3),
            "avg_r": round(self.avg_r, 3),
            "max_drawdown_r": round(self.max_drawdown_r, 3),
            "max_drawdown_pips": round(self.max_drawdown_pips, 2),
            "avg_winner_pips": round(self.avg_winner_pips, 2),
            "avg_loser_pips": round(self.avg_loser_pips, 2),
            "consecutive_wins_max": self.consecutive_wins_max,
            "consecutive_losses_max": self.consecutive_losses_max,
            "avg_score": round(self.avg_score, 1),
        }


def pip_size_for_symbol(symbol: str) -> float:
    if "JPY" in symbol.upper():
        return 0.01
    if symbol.upper() in {"XAUUSD", "XAGUSD"}:
        return 0.01
    return 0.0001


def apply_entry_costs(
    entry: float,
    direction: str,
    *,
    pip: float,
    config: ExecutionConfig,
) -> float:
    half_spread = (config.spread_pips * pip) / 2.0
    slip = config.slippage_pips * pip
    if direction == "buy":
        return entry + half_spread + slip
    return entry - half_spread - slip


def simulate_trade(
    *,
    direction: str,
    entry: float,
    stop_loss: float,
    take_profit: float,
    forward_bars: list,
    pip: float,
    score: int = 0,
    config: ExecutionConfig | None = None,
) -> SimulatedTrade:
    """Simulate one trade after the signal bar.

    ``forward_bars`` must be candles AFTER the signal bar (no lookahead into
    signal-bar intrabar path beyond the close entry assumption).
    """
    cfg = config or ExecutionConfig()
    direction = direction.lower()
    fill = apply_entry_costs(entry, direction, pip=pip, config=cfg)
    risk = abs(fill - stop_loss)
    if risk <= 0:
        risk = abs(entry - stop_loss) or pip

    outcome = "breakeven"
    exit_price = fill
    ambiguous = False
    bars_held = 0

    for bar in forward_bars:
        bars_held += 1
        if direction == "buy":
            hit_sl = bar.low <= stop_loss
            hit_tp = bar.high >= take_profit
            if hit_sl and hit_tp:
                ambiguous = True
                # Conservative: SL first — never pick the favorable outcome.
                outcome, exit_price = "loss", stop_loss
                break
            if hit_sl:
                outcome, exit_price = "loss", stop_loss
                break
            if hit_tp:
                outcome, exit_price = "win", take_profit
                break
        else:
            hit_sl = bar.high >= stop_loss
            hit_tp = bar.low <= take_profit
            if hit_sl and hit_tp:
                ambiguous = True
                outcome, exit_price = "loss", stop_loss
                break
            if hit_sl:
                outcome, exit_price = "loss", stop_loss
                break
            if hit_tp:
                outcome, exit_price = "win", take_profit
                break

    if outcome == "breakeven" and forward_bars:
        exit_price = forward_bars[-1].close
        pnl = (exit_price - fill) if direction == "buy" else (fill - exit_price)
        outcome = "win" if pnl > 0 else "loss" if pnl < 0 else "breakeven"

    pnl_price = (exit_price - fill) if direction == "buy" else (fill - exit_price)
    pnl_price -= cfg.commission_pips * pip
    pnl_pips = pnl_price / pip if pip else 0.0
    r_multiple = pnl_price / risk if risk else 0.0

    return SimulatedTrade(
        entry_price=fill,
        exit_price=exit_price,
        direction=direction,
        outcome=outcome,
        pnl_pips=pnl_pips,
        pnl_price=pnl_price,
        risk_price=risk,
        r_multiple=r_multiple,
        score=score,
        ambiguous=ambiguous,
        bars_held=bars_held,
    )


def compute_performance_metrics(trades: list[SimulatedTrade]) -> PerformanceMetrics:
    """Deterministic performance metrics with manually verifiable formulas."""
    m = PerformanceMetrics()
    m.total_trades = len(trades)
    if not trades:
        return m

    m.wins = sum(1 for t in trades if t.outcome == "win")
    m.losses = sum(1 for t in trades if t.outcome == "loss")
    m.breakeven = sum(1 for t in trades if t.outcome == "breakeven")
    m.win_rate = (m.wins / m.total_trades) * 100.0
    m.avg_score = sum(t.score for t in trades) / len(trades)

    winners = [t.pnl_pips for t in trades if t.outcome == "win"]
    losers = [t.pnl_pips for t in trades if t.outcome == "loss"]
    m.avg_winner_pips = sum(winners) / len(winners) if winners else 0.0
    m.avg_loser_pips = sum(losers) / len(losers) if losers else 0.0

    gross_profit = sum(t.pnl_price for t in trades if t.pnl_price > 0)
    gross_loss = abs(sum(t.pnl_price for t in trades if t.pnl_price < 0))
    m.profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else None

    r_vals = [t.r_multiple for t in trades]
    m.expectancy = sum(r_vals) / len(r_vals)
    m.avg_r = m.expectancy

    # Drawdown on cumulative R
    equity_r = [0.0]
    equity_pips = [0.0]
    for t in trades:
        equity_r.append(equity_r[-1] + t.r_multiple)
        equity_pips.append(equity_pips[-1] + t.pnl_pips)

    def _max_dd(curve: list[float]) -> float:
        peak = curve[0]
        max_dd = 0.0
        for eq in curve:
            if eq > peak:
                peak = eq
            dd = peak - eq
            if dd > max_dd:
                max_dd = dd
        return max_dd

    m.max_drawdown_r = _max_dd(equity_r)
    m.max_drawdown_pips = _max_dd(equity_pips)

    # Consecutive streaks
    cw = cl = max_cw = max_cl = 0
    for t in trades:
        if t.outcome == "win":
            cw += 1
            cl = 0
            max_cw = max(max_cw, cw)
        elif t.outcome == "loss":
            cl += 1
            cw = 0
            max_cl = max(max_cl, cl)
        else:
            cw = cl = 0
    m.consecutive_wins_max = max_cw
    m.consecutive_losses_max = max_cl
    return m

"""Backtesting engine — measures historical performance of scanner setups."""

from dataclasses import dataclass, field
from typing import Optional

from services.indicator_service.indicators import compute_all
from services.scanner_service.engine import DecisionEngine
from services.smc_service.smc import SMCEngine
from shared.types.models import (
    Candle,
    NewsContext,
    SignalDirection,
    Timeframe,
    TrendDirection,
)


@dataclass
class TradeResult:
    entry_price: float
    exit_price: float
    direction: str
    outcome: str  # win, loss, breakeven
    pnl_pips: float
    score: int


@dataclass
class BacktestReport:
    symbol: str
    timeframe: str
    min_score: int
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    breakeven: int = 0
    win_rate: float = 0.0
    avg_rr: float = 0.0
    max_drawdown: float = 0.0
    avg_score: float = 0.0
    trades: list[TradeResult] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "min_score": self.min_score,
            "total_trades": self.total_trades,
            "wins": self.wins,
            "losses": self.losses,
            "breakeven": self.breakeven,
            "win_rate": round(self.win_rate, 1),
            "avg_rr": round(self.avg_rr, 2),
            "max_drawdown": round(self.max_drawdown, 2),
            "avg_score": round(self.avg_score, 1),
            "sample_trades": [
                {"direction": t.direction, "outcome": t.outcome, "score": t.score, "pnl_pips": round(t.pnl_pips, 1)}
                for t in self.trades[-5:]
            ],
        }


class BacktestEngine:
    """Walk-forward backtest on candle history using the Decision Engine."""

    def __init__(self):
        self.engine = DecisionEngine()
        self.smc = SMCEngine()

    def run(
        self,
        symbol: str,
        candles: list[Candle],
        timeframe: Timeframe = Timeframe.H1,
        min_score: int = 70,
        forward_bars: int = 20,
    ) -> BacktestReport:
        report = BacktestReport(symbol=symbol, timeframe=timeframe.value, min_score=min_score)
        if len(candles) < 80:
            return report

        pip = 0.01 if "JPY" in symbol else (0.01 if symbol == "XAUUSD" else 0.0001)
        trades: list[TradeResult] = []
        equity_curve: list[float] = [0.0]
        cooldown = 0

        for i in range(60, len(candles) - forward_bars):
            if cooldown > 0:
                cooldown -= 1
                continue

            window = candles[: i + 1]
            indicators = compute_all(window, symbol, timeframe)
            smc_patterns = self.smc.detect_all(window[-50:], symbol, timeframe)

            mtf_trends: dict[str, TrendDirection] = {}
            if indicators.ema_20 and indicators.ema_50:
                if indicators.ema_20 > indicators.ema_50:
                    mtf_trends["H1"] = TrendDirection.BULLISH
                else:
                    mtf_trends["H1"] = TrendDirection.BEARISH

            signal = self.engine.evaluate(
                symbol=symbol,
                timeframe=timeframe,
                candles=window,
                indicators=indicators,
                smc_patterns=smc_patterns,
                mtf_trends=mtf_trends,
                news=NewsContext(score=10),
            )

            if signal.score < min_score or signal.direction == SignalDirection.NEUTRAL:
                continue
            if not signal.stop_loss or not signal.take_profit_1:
                continue

            entry = window[-1].close
            sl = signal.stop_loss
            tp = signal.take_profit_1
            direction = signal.direction.value

            outcome = "breakeven"
            exit_price = entry
            for bar in candles[i + 1 : i + 1 + forward_bars]:
                if direction == "buy":
                    if bar.low <= sl:
                        outcome, exit_price = "loss", sl
                        break
                    if bar.high >= tp:
                        outcome, exit_price = "win", tp
                        break
                else:
                    if bar.high >= sl:
                        outcome, exit_price = "loss", sl
                        break
                    if bar.low <= tp:
                        outcome, exit_price = "win", tp
                        break

            if outcome == "breakeven":
                exit_price = candles[min(i + forward_bars, len(candles) - 1)].close
                pnl = (exit_price - entry) if direction == "buy" else (entry - exit_price)
                outcome = "win" if pnl > 0 else "loss" if pnl < 0 else "breakeven"

            pnl_raw = (exit_price - entry) if direction == "buy" else (entry - exit_price)
            pnl_pips = pnl_raw / pip

            trades.append(TradeResult(
                entry_price=entry, exit_price=exit_price,
                direction=direction, outcome=outcome,
                pnl_pips=pnl_pips, score=signal.score,
            ))

            equity_curve.append(equity_curve[-1] + pnl_pips)
            cooldown = forward_bars // 2

        report.trades = trades
        report.total_trades = len(trades)
        if not trades:
            return report

        report.wins = sum(1 for t in trades if t.outcome == "win")
        report.losses = sum(1 for t in trades if t.outcome == "loss")
        report.breakeven = sum(1 for t in trades if t.outcome == "breakeven")
        report.win_rate = (report.wins / report.total_trades) * 100
        report.avg_score = sum(t.score for t in trades) / len(trades)

        rr_vals = []
        for t in trades:
            if t.outcome == "win" and t.pnl_pips > 0:
                rr_vals.append(abs(t.pnl_pips))
            elif t.outcome == "loss":
                rr_vals.append(0)
        if rr_vals:
            report.avg_rr = sum(rr_vals) / max(report.losses, 1) if report.losses else 1.5

        peak = equity_curve[0]
        max_dd = 0.0
        for eq in equity_curve:
            if eq > peak:
                peak = eq
            dd = peak - eq
            if dd > max_dd:
                max_dd = dd
        report.max_drawdown = max_dd

        return report

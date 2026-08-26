"""Backtesting engine — measures historical performance of scanner setups."""

from dataclasses import dataclass, field
from typing import Optional

from services.backtesting_service.execution import (
    ExecutionConfig,
    SimulatedTrade,
    compute_performance_metrics,
    pip_size_for_symbol,
    simulate_trade,
)
from services.quant_engine.pipeline import ANALYSIS_PIPELINE_VERSION, analyze_candle_window
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
    r_multiple: float = 0.0
    ambiguous: bool = False


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
    profit_factor: float | None = None
    expectancy: float = 0.0
    pipeline_version: str = ANALYSIS_PIPELINE_VERSION
    execution_config: dict = field(default_factory=dict)
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
            "avg_r": round(self.avg_rr, 2),
            "max_drawdown": round(self.max_drawdown, 2),
            "avg_score": round(self.avg_score, 1),
            "profit_factor": (
                round(self.profit_factor, 3) if self.profit_factor is not None else None
            ),
            "expectancy": round(self.expectancy, 3),
            "pipeline_version": self.pipeline_version,
            "execution_config": dict(self.execution_config),
            "sample_trades": [
                {
                    "direction": t.direction,
                    "outcome": t.outcome,
                    "score": t.score,
                    "pnl_pips": round(t.pnl_pips, 1),
                    "r_multiple": round(t.r_multiple, 3),
                    "ambiguous": t.ambiguous,
                }
                for t in self.trades[-5:]
            ],
        }


class BacktestEngine:
    """Walk-forward backtest using the canonical analysis pipeline."""

    def __init__(self, execution: ExecutionConfig | None = None):
        self.engine = DecisionEngine()
        self.smc = SMCEngine()
        self.execution = execution or ExecutionConfig()

    def run(
        self,
        symbol: str,
        candles: list[Candle],
        timeframe: Timeframe = Timeframe.H1,
        min_score: int = 70,
        forward_bars: int = 20,
        mtf_trends: Optional[dict[str, TrendDirection]] = None,
        htf_bars: Optional[dict[str, list[Candle]]] = None,
    ) -> BacktestReport:
        report = BacktestReport(
            symbol=symbol,
            timeframe=timeframe.value,
            min_score=min_score,
            pipeline_version=ANALYSIS_PIPELINE_VERSION,
            execution_config={
                "entry_mode": self.execution.entry_mode,
                "ambiguous_policy": self.execution.ambiguous_policy,
                "spread_pips": self.execution.spread_pips,
                "slippage_pips": self.execution.slippage_pips,
                "commission_pips": self.execution.commission_pips,
            },
        )
        if len(candles) < 80:
            return report

        pip = pip_size_for_symbol(symbol)
        simulated: list[SimulatedTrade] = []
        cooldown = 0

        # News is intentionally neutral in historical backtests unless the
        # caller injects a causal calendar (see docs — revised calendars leak).
        news = NewsContext(score=10)

        for i in range(60, len(candles) - forward_bars):
            if cooldown > 0:
                cooldown -= 1
                continue

            window = candles[: i + 1]
            # Causal HTF: rollup from window (or filter provided series) inside pipeline.
            window_htf = None
            if htf_bars:
                from services.quant_engine.pipeline.mtf_context import filter_completed_htf

                as_of = window[-1].timestamp
                window_htf = {
                    k: filter_completed_htf(v, as_of) for k, v in htf_bars.items()
                }

            bundle = analyze_candle_window(
                symbol,
                timeframe,
                window,
                mtf_trends=mtf_trends,
                htf_bars=window_htf,
                news=news,
                decision_engine=self.engine,
                smc_engine=self.smc,
                evaluate=True,
            )
            signal = bundle.signal
            if signal is None:
                continue
            if signal.score < min_score or signal.direction == SignalDirection.NEUTRAL:
                continue
            if not signal.stop_loss or not signal.take_profit_1:
                continue

            trade = simulate_trade(
                direction=signal.direction.value,
                entry=window[-1].close,
                stop_loss=signal.stop_loss,
                take_profit=signal.take_profit_1,
                forward_bars=candles[i + 1 : i + 1 + forward_bars],
                pip=pip,
                score=signal.score,
                config=self.execution,
            )
            simulated.append(trade)
            cooldown = forward_bars // 2

        metrics = compute_performance_metrics(simulated)
        report.trades = [
            TradeResult(
                entry_price=t.entry_price,
                exit_price=t.exit_price,
                direction=t.direction,
                outcome=t.outcome,
                pnl_pips=t.pnl_pips,
                score=t.score,
                r_multiple=t.r_multiple,
                ambiguous=t.ambiguous,
            )
            for t in simulated
        ]
        report.total_trades = metrics.total_trades
        report.wins = metrics.wins
        report.losses = metrics.losses
        report.breakeven = metrics.breakeven
        report.win_rate = metrics.win_rate
        report.avg_score = metrics.avg_score
        report.avg_rr = metrics.avg_r
        report.max_drawdown = metrics.max_drawdown_pips
        report.profit_factor = metrics.profit_factor
        report.expectancy = metrics.expectancy
        return report

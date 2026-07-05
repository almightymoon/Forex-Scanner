"""Validation engine — compare scanner predictions against actual outcomes."""

from services.validation_engine.metrics import ValidationMetrics
from services.validation_engine.report import ValidationReport
from services.validation_engine.storage import OutcomeStore, TrackedSignal, new_signal_id
from shared.types.models import Candle, ScannerSignal, SignalDirection


class SignalValidator:
    """
    Continuous feedback loop:
    Signal Generated → Trade Closed → Record Outcome → Update Statistics
    """

    def __init__(self, store: OutcomeStore | None = None):
        self.store = store or OutcomeStore()

    def register(self, signal: ScannerSignal) -> str:
        if not signal.entry_zone_low or not signal.stop_loss or not signal.take_profit_1:
            return ""
        entry = (signal.entry_zone_low + (signal.entry_zone_high or signal.entry_zone_low)) / 2
        patterns = [p.get("id", "") for p in (signal.detected_patterns or [])]
        tracked = TrackedSignal(
            id=new_signal_id(),
            symbol=signal.symbol,
            timeframe=signal.timeframe.value if hasattr(signal.timeframe, "value") else str(signal.timeframe),
            direction=signal.direction.value,
            score=signal.score,
            confidence=signal.confidence,
            entry_price=entry,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit_1,
            patterns=patterns,
        )
        return self.store.save(tracked)

    def evaluate_open_signals(
        self, symbol: str, candles: list[Candle], max_bars: int = 24
    ) -> list[TrackedSignal]:
        """Check open tracked signals against new candles and close if SL/TP hit."""
        closed: list[TrackedSignal] = []
        open_signals = [s for s in self.store.list_all(symbol) if s.outcome is None]

        for sig in open_signals:
            outcome = self._check_outcome(sig, candles[-max_bars:])
            if outcome:
                sig.outcome = outcome["outcome"]
                sig.pnl_pips = outcome["pnl_pips"]
                sig.exit_price = outcome["exit_price"]
                sig.closed_at = candles[-1].timestamp.isoformat() if candles else None
                self.store.update(sig)
                closed.append(sig)
        return closed

    def report(self, symbol: str | None = None) -> ValidationReport:
        signals = self.store.list_all(symbol, closed_only=True)
        metrics = self._compute_metrics(signals)
        if not symbol:
            all_signals = self.store.list_all(closed_only=False)
            metrics.total_signals = len(all_signals)

        recommendations = self._recommendations(metrics)
        recent = [
            {
                "symbol": s.symbol,
                "direction": s.direction,
                "score": s.score,
                "outcome": s.outcome,
                "pnl_pips": round(s.pnl_pips, 1),
            }
            for s in signals[:10]
        ]
        scope = symbol.upper() if symbol else "global"
        return ValidationReport(scope=scope, metrics=metrics, recent_outcomes=recent, recommendations=recommendations)

    def _check_outcome(self, sig: TrackedSignal, bars: list[Candle]) -> dict | None:
        if not bars:
            return None
        pip = 0.01 if "JPY" in sig.symbol else (0.01 if sig.symbol == "XAUUSD" else 0.0001)

        for bar in bars:
            if sig.direction == "buy":
                if bar.low <= sig.stop_loss:
                    pnl = (sig.stop_loss - sig.entry_price) / pip
                    return {"outcome": "loss", "pnl_pips": pnl, "exit_price": sig.stop_loss}
                if bar.high >= sig.take_profit:
                    pnl = (sig.take_profit - sig.entry_price) / pip
                    return {"outcome": "win", "pnl_pips": pnl, "exit_price": sig.take_profit}
            else:
                if bar.high >= sig.stop_loss:
                    pnl = (sig.entry_price - sig.stop_loss) / pip
                    return {"outcome": "loss", "pnl_pips": pnl, "exit_price": sig.stop_loss}
                if bar.low <= sig.take_profit:
                    pnl = (sig.entry_price - sig.take_profit) / pip
                    return {"outcome": "win", "pnl_pips": pnl, "exit_price": sig.take_profit}
        return None

    def _compute_metrics(self, closed: list[TrackedSignal]) -> ValidationMetrics:
        m = ValidationMetrics()
        m.closed_signals = len(closed)
        if not closed:
            return m

        wins = [s for s in closed if s.outcome == "win"]
        losses = [s for s in closed if s.outcome == "loss"]
        m.wins = len(wins)
        m.losses = len(losses)
        m.breakeven = len(closed) - m.wins - m.losses
        m.win_rate = (m.wins / len(closed)) * 100 if closed else 0.0

        if wins:
            m.avg_score_winners = sum(s.score for s in wins) / len(wins)
            m.avg_confidence_winners = sum(s.confidence for s in wins) / len(wins)
        if losses:
            m.avg_score_losers = sum(s.score for s in losses) / len(losses)
            m.avg_confidence_losers = sum(s.confidence for s in losses) / len(losses)

        bands: dict[str, list[str]] = {}
        for s in closed:
            band = f"{(s.score // 10) * 10}-{(s.score // 10) * 10 + 9}"
            bands.setdefault(band, []).append(s.outcome or "")
        for band, outcomes in bands.items():
            wins_in_band = sum(1 for o in outcomes if o == "win")
            m.precision_by_score_band[band] = round((wins_in_band / len(outcomes)) * 100, 1)

        return m

    @staticmethod
    def _recommendations(metrics: ValidationMetrics) -> list[str]:
        recs: list[str] = []
        if metrics.closed_signals < 20:
            recs.append("Need more closed trades before adjusting scoring weights")
            return recs
        if metrics.win_rate < 45:
            recs.append("Win rate below 45% — review min score threshold or SMC quality filters")
        if metrics.avg_score_losers > metrics.avg_score_winners and metrics.losses > 5:
            recs.append("Losing trades score higher than winners — tighten structure/OB quality gates")
        elite_band = metrics.precision_by_score_band.get("90-99", 0)
        if elite_band and elite_band >= 70:
            recs.append(f"90+ score band shows {elite_band}% precision — prioritize elite setups")
        return recs

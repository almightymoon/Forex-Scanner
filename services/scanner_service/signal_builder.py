"""Builds scanner signals from prepared scan context."""

from services.ai_service.explainer import AIExplainer
from services.event_bus import EventTypes, get_event_bus
from services.scanner_service.data_loader import ScanContext
from services.scanner_service.decision_engine import DecisionEngine
from services.strategy_engine import StrategyEngine
from shared.config import get_scanner_config
from shared.types.models import ScannerSignal, to_dict


class SignalBuilder:
    """Runs the decision engine, strategies, events, and optional AI explanation."""

    def __init__(self, decision_engine=None, ai_explainer=None, strategy_engine=None):
        self.decision_engine = decision_engine or DecisionEngine()
        self.ai_explainer = ai_explainer or AIExplainer()
        self.strategy_engine = strategy_engine or StrategyEngine()
        self._bus = get_event_bus()
        self._stream = get_scanner_config().event_stream

    def build(self, ctx: ScanContext) -> ScannerSignal:
        return self.decision_engine.evaluate(
            symbol=ctx.symbol,
            timeframe=ctx.timeframe,
            candles=ctx.candles,
            indicators=ctx.indicators,
            smc_patterns=ctx.smc_patterns,
            mtf_trends=ctx.mtf_trends,
            news=ctx.news,
        )

    async def build_with_ai(self, ctx: ScanContext) -> ScannerSignal:
        signal = self.build(ctx)
        signal.ai_explanation = await self.ai_explainer.explain(signal)
        await self._emit_events(signal, ctx)
        return signal

    async def _emit_events(self, signal: ScannerSignal, ctx: ScanContext) -> None:
        if not get_scanner_config().enable_event_bus:
            return

        await self._bus.publish(
            self._stream,
            EventTypes.SCAN_COMPLETED,
            {
                "symbol": signal.symbol,
                "score": signal.score,
                "confidence": signal.confidence,
                "direction": signal.direction.value,
            },
        )

        if signal.score >= get_scanner_config().scoring.min_alert_score:
            await self._bus.publish(
                self._stream,
                EventTypes.SIGNAL_ALERT,
                to_dict(signal),
            )

        await self.strategy_engine.run_for_signal(
            signal, ctx.indicators, ctx.smc_patterns
        )

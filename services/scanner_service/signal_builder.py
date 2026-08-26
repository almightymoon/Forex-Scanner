"""Builds scanner signals from prepared scan context via canonical pipeline."""

import asyncio

from services.ai_service.explainer import AIExplainer
from services.event_bus import EventTypes, get_event_bus
from services.quant_engine.pipeline import analyze_candle_window
from services.quant_engine.pipeline.htf_drift import maybe_log_htf_drift
from services.scanner_service.data_loader import ScanContext
from services.scanner_service.decision_engine import DecisionEngine
from services.strategy_engine import StrategyEngine
from services.validation_engine import SignalValidator
from shared.config import get_scanner_config
from shared.types.models import ScannerSignal, to_dict


class SignalBuilder:
    """Runs the canonical analysis pipeline, strategies, events, and AI."""

    def __init__(self, decision_engine=None, ai_explainer=None, strategy_engine=None, validator=None):
        self.decision_engine = decision_engine or DecisionEngine()
        self.ai_explainer = ai_explainer or AIExplainer()
        self.strategy_engine = strategy_engine or StrategyEngine()
        self.validator = validator or SignalValidator()
        self._bus = get_event_bus()
        self._stream = get_scanner_config().event_stream

    def build(self, ctx: ScanContext) -> ScannerSignal:
        # Observational only — never mutates candles/htf_bars or analysis inputs.
        maybe_log_htf_drift(
            symbol=ctx.symbol,
            ltf_candles=ctx.candles,
            provider_htf=ctx.htf_bars,
        )
        bundle = analyze_candle_window(
            ctx.symbol,
            ctx.timeframe,
            ctx.candles,
            htf_bars=ctx.htf_bars,
            news=ctx.news,
            decision_engine=self.decision_engine,
            evaluate=True,
        )
        # Keep ScanContext in sync for strategy / event consumers.
        ctx.indicators = bundle.indicators
        ctx.smc_patterns = list(bundle.smc_patterns)
        ctx.mtf_trends = dict(bundle.mtf_trends)
        ctx.confirmed_swings = list(bundle.confirmed_swings)
        ctx.structure_snapshot = bundle.structure_snapshot
        ctx.structure_input = bundle.structure_input
        ctx.swing_version = bundle.swing_version
        ctx.pipeline_version = bundle.pipeline_version

        signal = bundle.signal
        assert signal is not None
        if signal.score >= get_scanner_config().scoring.min_alert_score:
            self.validator.register(signal)
            self.validator.evaluate_open_signals(ctx.symbol, ctx.candles)
        return signal

    async def build_with_ai(self, ctx: ScanContext) -> ScannerSignal:
        # CPU-heavy SMC/quant work must not block the asyncio event loop
        # (otherwise /health and dashboard fetches time out).
        signal = await asyncio.to_thread(self.build, ctx)
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

        if ctx.indicators is not None:
            await self.strategy_engine.run_for_signal(
                signal, ctx.indicators, ctx.smc_patterns
            )

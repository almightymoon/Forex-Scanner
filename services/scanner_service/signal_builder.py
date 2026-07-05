"""Builds scanner signals from prepared scan context."""

from services.ai_service.explainer import AIExplainer
from services.scanner_service.data_loader import ScanContext
from services.scanner_service.decision_engine import DecisionEngine
from shared.types.models import ScannerSignal


class SignalBuilder:
    """Runs the decision engine and optionally enriches with AI explanation."""

    def __init__(self, decision_engine=None, ai_explainer=None):
        self.decision_engine = decision_engine or DecisionEngine()
        self.ai_explainer = ai_explainer or AIExplainer()

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
        return signal

"""Strategy engine — run user strategies and emit alerts."""

from shared.types.models import IndicatorValues, SMCPattern, ScannerSignal

from services.event_bus import EventTypes, get_event_bus
from shared.config import get_scanner_config

from .evaluator import StrategyEvaluator
from .storage import StrategyStorage


class StrategyEngine:
    def __init__(self, storage: StrategyStorage | None = None):
        self.storage = storage or StrategyStorage()
        self.evaluator = StrategyEvaluator()
        self._bus = get_event_bus()
        self._stream = get_scanner_config().event_stream

    async def run_for_signal(
        self,
        signal: ScannerSignal,
        indicators: IndicatorValues,
        smc_patterns: list[SMCPattern],
    ) -> list[dict]:
        triggered = []
        for strategy in self.storage.list_all():
            if strategy.symbols and signal.symbol not in strategy.symbols:
                continue
            matched, reasons = self.evaluator.evaluate(
                strategy, indicators, smc_patterns, signal.score
            )
            if matched:
                entry = {
                    "strategy_id": strategy.id,
                    "strategy_name": strategy.name,
                    "action": strategy.action,
                    "symbol": signal.symbol,
                    "reasons": reasons,
                }
                triggered.append(entry)
                await self._bus.publish(
                    self._stream,
                    EventTypes.STRATEGY_TRIGGERED,
                    entry,
                    source="strategy_engine",
                )
        return triggered

    def list_strategies(self, user_id: str) -> list[dict]:
        return [s.to_dict() for s in self.storage.list_for_user(user_id)]

    def create_strategy(self, strategy, user_id: str) -> dict:
        strategy.user_id = user_id
        saved = self.storage.save(strategy)
        return saved.to_dict()

    def delete_strategy(self, strategy_id: str, user_id: str) -> bool:
        return self.storage.delete(strategy_id, user_id)

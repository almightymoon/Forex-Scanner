"""Scanner pipeline — orchestrates staged scan flow."""

import asyncio
import logging
from datetime import datetime, timezone

from services.ai_service.explainer import AIExplainer
from services.backtesting_service.backtester import BacktestEngine
from services.market_data_service.provider import FOREX_PAIRS
from services.notification_service.notifier import NotificationService
from services.scanner_service.data_loader import DataLoader
from services.scanner_service.signal_builder import SignalBuilder
from shared.db_factory import get_database
from shared.types.models import ScannerSignal, Timeframe

logger = logging.getLogger("fxnav.scanner")


class ScannerPipeline:
    """
    ScannerPipeline
      → DataLoader
      → SignalBuilder (DecisionEngine → independent engines)
      → persistence & alerts
    """

    def __init__(self, data_loader=None):
        self.data_loader = data_loader or DataLoader()
        self.signal_builder = SignalBuilder()
        self.notifier = NotificationService()
        self.backtester = BacktestEngine()
        self.db = get_database()
        self._results: list[ScannerSignal] = []
        self._running = False
        self._backtest_cache: dict[str, dict] = {}

    @property
    def market_data(self):
        return self.data_loader.market_data

    @property
    def news_service(self):
        return self.data_loader.news_service

    async def scan_symbol(
        self, symbol: str, timeframe: Timeframe = Timeframe.H1,
        with_ai: bool = True, with_backtest: bool = False,
    ) -> ScannerSignal | None:
        ctx = await self.data_loader.load(symbol, timeframe)
        if not ctx:
            return None

        if with_ai:
            signal = await self.signal_builder.build_with_ai(ctx)
        else:
            signal = self.signal_builder.build(ctx)

        if with_backtest:
            cache_key = f"{symbol}_{timeframe.value}"
            if cache_key not in self._backtest_cache:
                report = self.backtester.run(symbol, ctx.candles, timeframe)
                result = report.to_dict()
                self._backtest_cache[cache_key] = result
                if hasattr(self.db, "save_backtest_result"):
                    self.db.save_backtest_result(symbol, timeframe.value, 70, result)

        return signal

    async def run_backtest(
        self, symbol: str, timeframe: Timeframe = Timeframe.H1, min_score: int = 70
    ) -> dict:
        candles = await self.market_data.get_candles(symbol, timeframe, 300)
        report = self.backtester.run(symbol, candles, timeframe, min_score)
        result = report.to_dict()
        if hasattr(self.db, "save_backtest_result"):
            self.db.save_backtest_result(symbol, timeframe.value, min_score, result)
        self._backtest_cache[f"{symbol}_{timeframe.value}"] = result
        return result

    async def get_backtest(self, symbol: str, timeframe: str = "H1") -> dict | None:
        cache_key = f"{symbol}_{timeframe}"
        if cache_key in self._backtest_cache:
            return self._backtest_cache[cache_key]
        if hasattr(self.db, "get_latest_backtest"):
            cached = self.db.get_latest_backtest(symbol, timeframe)
            if cached:
                return cached
        return await self.run_backtest(symbol, Timeframe(timeframe))

    async def scan_all(
        self,
        symbols: list[str] | None = None,
        timeframe: Timeframe = Timeframe.H1,
        min_score: int = 60,
        save: bool = True,
        alert_threshold: int = 80,
    ) -> list[ScannerSignal]:
        await self.data_loader.load_events()
        symbols = symbols or FOREX_PAIRS
        sem = asyncio.Semaphore(6)

        async def _scan_one(symbol: str) -> ScannerSignal | None:
            async with sem:
                try:
                    return await self.scan_symbol(symbol, timeframe, with_ai=True)
                except Exception as exc:
                    logger.warning("Scan failed for %s: %s", symbol, exc)
                    return None

        results = await asyncio.gather(*[_scan_one(s) for s in symbols])
        signals = [r for r in results if r and r.score >= min_score]
        signals.sort(key=lambda s: s.score, reverse=True)
        self._results = signals

        if save and signals:
            self.db.save_scan_results(signals)

        for signal in signals:
            if signal.score >= alert_threshold:
                await self.notifier.notify_signal(signal, methods=["console"])

        return signals

    async def run_continuous(self, interval: int = 60, min_score: int = 80) -> None:
        self._running = True
        while self._running:
            signals = await self.scan_all(min_score=min_score, alert_threshold=min_score)
            print(f"[{datetime.now(timezone.utc).isoformat()}] Scan complete: {len(signals)} signals")
            for s in signals[:5]:
                label = "GOLD" if s.symbol == "XAUUSD" else s.symbol
                print(f"  {label} {s.direction.value.upper()} {s.score}/100 ({s.rating.value})")
            await asyncio.sleep(interval)

    def stop(self):
        self._running = False

    @property
    def latest_results(self) -> list[ScannerSignal]:
        return self._results


if __name__ == "__main__":
    pipeline = ScannerPipeline()
    asyncio.run(pipeline.run_continuous())

"""Scanner pipeline — orchestrates data → indicators → SMC → decision engine."""

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from services.ai_service.explainer import AIExplainer
from services.backtesting_service.backtester import BacktestEngine
from services.indicator_service.indicators import compute_all
from services.market_data_service.provider import FOREX_PAIRS
from services.market_data_service.live import create_market_data_provider
from services.news_service.calendar import NewsService
from services.notification_service.notifier import NotificationService
from services.scanner_service.engine import DecisionEngine
from services.smc_service.smc import SMCEngine
from shared.db_factory import get_database
from shared.types.models import ScannerSignal, Timeframe, TrendDirection


class ScannerPipeline:
    """Continuous scanning pipeline with live data, news filter, DB persistence, and alerts."""

    def __init__(self):
        self.market_data = create_market_data_provider()
        self.decision_engine = DecisionEngine()
        self.smc_engine = SMCEngine()
        self.news_service = NewsService()
        self.notifier = NotificationService()
        self.ai_explainer = AIExplainer()
        self.backtester = BacktestEngine()
        self.db = get_database()
        self._results: list[ScannerSignal] = []
        self._running = False
        self._events: list[dict] = []
        self._backtest_cache: dict[str, dict] = {}

    async def _load_news(self):
        self._events = await self.news_service.get_events()

    async def scan_symbol(
        self, symbol: str, timeframe: Timeframe = Timeframe.H1,
        with_ai: bool = True, with_backtest: bool = False,
    ) -> ScannerSignal | None:
        candles = await self.market_data.get_candles(symbol, timeframe, 200)
        if len(candles) < 50:
            return None

        indicators = compute_all(candles, symbol, timeframe)
        smc_patterns = self.smc_engine.detect_all(candles, symbol, timeframe)

        mtf_trends: dict[str, TrendDirection] = {}
        for tf in [Timeframe.M15, Timeframe.H4, Timeframe.D1]:
            tf_candles = await self.market_data.get_candles(symbol, tf, 100)
            if len(tf_candles) >= 50:
                tf_ind = compute_all(tf_candles, symbol, tf)
                if tf_ind.ema_20 and tf_ind.ema_50:
                    if tf_ind.ema_20 > tf_ind.ema_50:
                        mtf_trends[tf.value] = TrendDirection.BULLISH
                    elif tf_ind.ema_20 < tf_ind.ema_50:
                        mtf_trends[tf.value] = TrendDirection.BEARISH
                    else:
                        mtf_trends[tf.value] = TrendDirection.RANGING

        if not self._events:
            await self._load_news()
        news = self.news_service.evaluate_news_risk(symbol, self._events)

        signal = self.decision_engine.evaluate(
            symbol=symbol,
            timeframe=timeframe,
            candles=candles,
            indicators=indicators,
            smc_patterns=smc_patterns,
            mtf_trends=mtf_trends,
            news=news,
        )

        if with_ai:
            signal.ai_explanation = await self.ai_explainer.explain(signal)

        if with_backtest:
            cache_key = f"{symbol}_{timeframe.value}"
            if cache_key not in self._backtest_cache:
                report = self.backtester.run(symbol, candles, timeframe)
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
        await self._load_news()
        symbols = symbols or FOREX_PAIRS
        tasks = [self.scan_symbol(s, timeframe) for s in symbols]
        results = await asyncio.gather(*tasks)
        signals = [r for r in results if r and r.score >= min_score]
        signals.sort(key=lambda s: s.score, reverse=True)
        self._results = signals

        if save and signals:
            self.db.save_scan_results(signals)

        for signal in signals:
            if signal.score >= alert_threshold:
                await self.notifier.notify_signal(signal, methods=["console"])

        return signals

    async def run_continuous(
        self, interval: int = 60, min_score: int = 80
    ) -> None:
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

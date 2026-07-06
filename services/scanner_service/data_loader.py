"""Loads market data, indicators, SMC patterns, and news for scanning."""

import asyncio
import logging
from dataclasses import dataclass

from services.indicator_service.indicators import compute_all
from services.market_data_service.exceptions import MarketDataProviderError
from services.market_data_service.factory import create_market_data_provider
from services.news_service.calendar import NewsService
from services.smc_service.smc import SMCEngine
from shared.types.models import (
    Candle,
    IndicatorValues,
    NewsContext,
    SMCPattern,
    Timeframe,
    TrendDirection,
)

logger = logging.getLogger("fxnav.scanner")

# Limit concurrent candle fetches to avoid blowing through free-tier rate limits.
_CANDLE_SEMAPHORE = asyncio.Semaphore(4)


@dataclass
class ScanContext:
    symbol: str
    timeframe: Timeframe
    candles: list[Candle]
    indicators: IndicatorValues
    smc_patterns: list[SMCPattern]
    mtf_trends: dict[str, TrendDirection]
    news: NewsContext


class DataLoader:
    """Fetches and prepares all inputs for the decision engine."""

    def __init__(self, market_data=None, smc_engine=None, news_service=None):
        self.market_data = market_data or create_market_data_provider()
        self.smc_engine = smc_engine or SMCEngine()
        self.news_service = news_service or NewsService()
        self._events: list[dict] = []

    async def load_events(self):
        self._events = await self.news_service.get_events()

    async def load(
        self, symbol: str, timeframe: Timeframe = Timeframe.H1
    ) -> ScanContext | None:
        try:
            async with _CANDLE_SEMAPHORE:
                candles = await self.market_data.get_candles(symbol, timeframe, 200)
        except MarketDataProviderError as exc:
            logger.warning("Skipping %s %s — market data unavailable: %s", symbol, timeframe.value, exc)
            return None

        if len(candles) < 50:
            return None

        indicators = compute_all(candles, symbol, timeframe)
        smc_patterns = self.smc_engine.detect_all(candles, symbol, timeframe)
        mtf_trends = await self._load_mtf_trends(symbol)

        if not self._events:
            await self.load_events()
        news = self.news_service.evaluate_news_risk(symbol, self._events)

        return ScanContext(
            symbol=symbol,
            timeframe=timeframe,
            candles=candles,
            indicators=indicators,
            smc_patterns=smc_patterns,
            mtf_trends=mtf_trends,
            news=news,
        )

    async def _fetch_candles_safe(self, symbol: str, timeframe: Timeframe, count: int) -> list[Candle]:
        try:
            async with _CANDLE_SEMAPHORE:
                return await self.market_data.get_candles(symbol, timeframe, count)
        except MarketDataProviderError as exc:
            logger.debug("MTF fetch failed for %s %s: %s", symbol, timeframe.value, exc)
            return []

    async def _load_mtf_trends(self, symbol: str) -> dict[str, TrendDirection]:
        trends: dict[str, TrendDirection] = {}
        for tf in [Timeframe.M15, Timeframe.H4, Timeframe.D1]:
            tf_candles = await self._fetch_candles_safe(symbol, tf, 100)
            if len(tf_candles) < 50:
                continue
            tf_ind = compute_all(tf_candles, symbol, tf)
            if tf_ind.ema_20 and tf_ind.ema_50:
                if tf_ind.ema_20 > tf_ind.ema_50:
                    trends[tf.value] = TrendDirection.BULLISH
                elif tf_ind.ema_20 < tf_ind.ema_50:
                    trends[tf.value] = TrendDirection.BEARISH
                else:
                    trends[tf.value] = TrendDirection.RANGING
        return trends

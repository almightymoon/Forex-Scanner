"""Loads market data for scanning — data preparation only.

Analysis (swings / structure / liquidity / SMC / decision) runs exclusively
through :func:`services.quant_engine.pipeline.analyze_candle_window` in
``SignalBuilder``.
"""

import asyncio
import logging
from dataclasses import dataclass, field

from services.market_data_service.exceptions import MarketDataProviderError
from services.market_data_service.factory import create_market_data_provider
from services.news_service.calendar import NewsService
from services.quant_engine.market_structure.models import StructureSnapshot
from services.quant_engine.pipeline import ANALYSIS_PIPELINE_VERSION
from services.quant_engine.swings.boundary import SCAN_SWING_VERSION, ScanStructureInput
from shared.types.models import (
    Candle,
    IndicatorValues,
    NewsContext,
    SMCPattern,
    Timeframe,
    TrendDirection,
)
from swing_engine.models import DetectedSwing

logger = logging.getLogger("fxnav.scanner")

_CANDLE_SEMAPHORE = asyncio.Semaphore(4)

# HTF series fetched for live MTF (provider). Gaps filled by rollup in pipeline.
_LIVE_HTF = (Timeframe.M15, Timeframe.H4, Timeframe.D1)


@dataclass
class ScanContext:
    """Prepared scan input + optional analytical artifacts after pipeline run."""

    symbol: str
    timeframe: Timeframe
    candles: list[Candle]
    news: NewsContext
    htf_bars: dict[str, list[Candle]] = field(default_factory=dict)
    # Filled by SignalBuilder via analyze_candle_window:
    indicators: IndicatorValues | None = None
    smc_patterns: list[SMCPattern] = field(default_factory=list)
    mtf_trends: dict[str, TrendDirection] = field(default_factory=dict)
    confirmed_swings: list[DetectedSwing] = field(default_factory=list)
    structure_snapshot: StructureSnapshot | None = None
    swing_version: str = SCAN_SWING_VERSION
    structure_input: ScanStructureInput | None = None
    pipeline_version: str = ANALYSIS_PIPELINE_VERSION


class DataLoader:
    """Fetches candles, HTF series, and news. Does not run analysis engines."""

    def __init__(self, market_data=None, smc_engine=None, news_service=None):
        self.market_data = market_data or create_market_data_provider()
        # smc_engine retained for DI compatibility; analysis is in SignalBuilder.
        self.smc_engine = smc_engine
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
            logger.warning(
                "Skipping %s %s — market data unavailable: %s",
                symbol,
                timeframe.value,
                exc,
            )
            return None

        if len(candles) < 50:
            return None

        htf_bars = await self._load_htf_bars(symbol, primary=timeframe)

        if not self._events:
            await self.load_events()
        news = self.news_service.evaluate_news_risk(symbol, self._events)

        return ScanContext(
            symbol=symbol,
            timeframe=timeframe,
            candles=candles,
            news=news,
            htf_bars=htf_bars,
        )

    async def _fetch_candles_safe(
        self, symbol: str, timeframe: Timeframe, count: int
    ) -> list[Candle]:
        try:
            async with _CANDLE_SEMAPHORE:
                return await self.market_data.get_candles(symbol, timeframe, count)
        except MarketDataProviderError as exc:
            logger.debug("HTF fetch failed for %s %s: %s", symbol, timeframe.value, exc)
            return []

    async def _load_htf_bars(
        self, symbol: str, *, primary: Timeframe
    ) -> dict[str, list[Candle]]:
        """Fetch provider HTF series (causal filter applied later in pipeline)."""
        bars: dict[str, list[Candle]] = {}
        for tf in _LIVE_HTF:
            if tf is primary:
                continue
            series = await self._fetch_candles_safe(symbol, tf, 100)
            if series:
                bars[tf.value] = series
        return bars

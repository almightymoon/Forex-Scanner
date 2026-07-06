"""Main orchestrator for the market data collector."""

from datetime import datetime, timezone
from typing import Optional

from services.data_collector.config import get_collector_config
from services.data_collector.database import CollectorDatabase, get_collector_database
from services.data_collector.downloader import DataDownloader
from services.data_collector.health import CollectorHealth
from services.data_collector.logger import get_logger
from services.data_collector.models import CollectionJob, JobType
from services.data_collector.providers.base_provider import BaseDataProvider
from services.data_collector.providers.dukascopy import DukascopyDataProvider
from services.data_collector.providers.mt5 import MT5DataProvider
from services.data_collector.scheduler import CollectionScheduler
from services.data_collector.symbols import SymbolRegistry
from services.data_collector.validator import DataValidator
from shared.types.models import Timeframe

logger = get_logger("collector")

PROVIDER_REGISTRY: dict[str, type[BaseDataProvider]] = {
    "mt5": MT5DataProvider,
    "dukascopy": DukascopyDataProvider,
}


class DataCollector:
    """
    Single entry point for market data collection.

    Workflow:
      1. Initialize database + symbol registry
      2. Connect enabled providers
      3. Schedule jobs (historical / incremental / live)
      4. Download → normalize → validate → persist
      5. Report health
    """

    def __init__(
        self,
        database: Optional[CollectorDatabase] = None,
        providers: Optional[list[BaseDataProvider]] = None,
    ):
        self.config = get_collector_config()
        self.database = database or get_collector_database()
        self.registry = SymbolRegistry()
        self.validator = DataValidator()
        self.providers: dict[str, BaseDataProvider] = {}
        self.downloaders: dict[str, DataDownloader] = {}
        self.health = CollectorHealth(self.database)
        self.scheduler = CollectionScheduler(handler=self._handle_job)

        if providers:
            for p in providers:
                self._register_provider(p)
        else:
            self._load_providers_from_config()

    def _load_providers_from_config(self) -> None:
        if self.config.providers.mt5.enabled:
            self._register_provider(MT5DataProvider())
        if self.config.providers.dukascopy.enabled:
            self._register_provider(DukascopyDataProvider())

    def _register_provider(self, provider: BaseDataProvider) -> None:
        self.providers[provider.name] = provider
        self.downloaders[provider.name] = DataDownloader(
            provider, self.database, self.validator
        )
        self.health.providers = list(self.providers.values())

    @classmethod
    def create_provider(cls, name: str) -> BaseDataProvider:
        factory = PROVIDER_REGISTRY.get(name.lower())
        if not factory:
            raise ValueError(f"Unknown provider: {name}. Available: {list(PROVIDER_REGISTRY)}")
        return factory()

    async def initialize(self) -> None:
        """Sync symbols and connect all enabled providers."""
        count = self.database.sync_symbols(self.registry)
        logger.info("symbol registry synced", extra={"collector_fields": {"count": count}})

        for name, provider in self.providers.items():
            connected = await provider.connect()
            status = await provider.health()
            self.database.update_provider_status(status)
            logger.info(
                "provider initialized",
                extra={"collector_fields": {
                    "provider": name, "connected": connected, "state": status.state.value,
                }},
            )

    async def shutdown(self) -> None:
        for provider in self.providers.values():
            await provider.disconnect()

    async def collect_historical(
        self,
        provider_name: str,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> tuple[int, int]:
        downloader = self._get_downloader(provider_name)
        return await downloader.download_historical(symbol, timeframe, start, end)

    async def collect_incremental(
        self,
        provider_name: str,
        symbol: str,
        timeframe: Timeframe,
        lookback_hours: int = 24,
    ) -> tuple[int, int]:
        downloader = self._get_downloader(provider_name)
        return await downloader.download_incremental(symbol, timeframe, lookback_hours)

    def schedule_incremental_matrix(self, provider_name: str) -> list[CollectionJob]:
        return self.scheduler.schedule_full_matrix(
            provider_name,
            self.config.symbols,
            self.config.timeframes,
            JobType.INCREMENTAL_UPDATE,
        )

    async def run_scheduled_jobs(self) -> int:
        return await self.scheduler.run_pending()

    async def drain_jobs(self) -> None:
        await self.scheduler.drain()

    async def _handle_job(self, job: CollectionJob) -> None:
        downloader = self._get_downloader(job.provider)

        if job.job_type == JobType.HISTORICAL_IMPORT:
            if not job.start_time or not job.end_time:
                raise ValueError("Historical job requires start_time and end_time")
            imported, rejected = await downloader.download_historical(
                job.symbol, job.timeframe, job.start_time, job.end_time
            )
        elif job.job_type == JobType.INCREMENTAL_UPDATE:
            imported, rejected = await downloader.download_incremental(
                job.symbol, job.timeframe
            )
        elif job.job_type == JobType.LIVE_POLL:
            provider = self.providers[job.provider]
            async for _tick in provider.stream_live([job.symbol]):
                pass  # Milestone 2: persist ticks
            imported, rejected = 0, 0
        else:
            raise ValueError(f"Unknown job type: {job.job_type}")

        job.rows_imported = imported
        job.rows_rejected = rejected

        status = await self.providers[job.provider].health()
        self.database.update_provider_status(status)

    def _get_downloader(self, provider_name: str) -> DataDownloader:
        downloader = self.downloaders.get(provider_name)
        if not downloader:
            raise ValueError(f"Provider not registered: {provider_name}")
        return downloader

    def get_health_snapshot(self) -> dict:
        return self.health.snapshot()

    def get_candles(
        self,
        symbol: str,
        timeframe: Timeframe,
        limit: int = 200,
    ):
        """Read path for downstream consumers (scanner in Milestone 2+)."""
        return self.database.get_candles(symbol, timeframe, limit=limit)

"""Download historical and incremental data from providers."""

import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from services.data_collector.database import CollectorDatabase
from services.data_collector.logger import get_logger, log_collection
from services.data_collector.models import CollectionLogEntry, JobType
from services.data_collector.normalizer import DataNormalizer
from services.data_collector.providers.base_provider import BaseDataProvider
from services.data_collector.validator import DataValidator
from shared.types.models import Timeframe

logger = get_logger("downloader")


class DataDownloader:
    """Orchestrates provider download → normalize → validate → persist."""

    def __init__(
        self,
        provider: BaseDataProvider,
        database: CollectorDatabase,
        validator: Optional[DataValidator] = None,
    ):
        self.provider = provider
        self.database = database
        self.validator = validator or DataValidator()
        self.normalizer = DataNormalizer(provider.name)

    async def download_historical(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> tuple[int, int]:
        """Full historical import for a symbol/timeframe range."""
        return await self._run_download(
            symbol, timeframe, start, end, JobType.HISTORICAL_IMPORT
        )

    async def download_incremental(
        self,
        symbol: str,
        timeframe: Timeframe,
        lookback_hours: int = 24,
    ) -> tuple[int, int]:
        """Fetch candles since the last stored timestamp (or lookback window)."""
        end = datetime.now(timezone.utc)
        latest = self.database.get_latest_timestamp(symbol, timeframe)
        if latest:
            start = latest - timedelta(seconds=DataNormalizer.expected_interval_seconds(timeframe))
        else:
            start = end - timedelta(hours=lookback_hours)

        return await self._run_download(
            symbol, timeframe, start, end, JobType.INCREMENTAL_UPDATE
        )

    async def _run_download(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
        job_type: JobType,
    ) -> tuple[int, int]:
        t0 = time.perf_counter()
        rows_imported = 0
        rows_rejected = 0
        status = "completed"
        message = ""

        try:
            raw = await self.provider.download_history(symbol, timeframe, start, end)
            normalized = self.normalizer.normalize_candles(raw)
            result = self.validator.validate_candles(normalized)

            rows_rejected = len(result.rejected)
            rows_imported = self.database.insert_candles(result.valid)

            if result.warnings:
                message = "; ".join(result.warnings[:3])
                if len(result.warnings) > 3:
                    message += f" (+{len(result.warnings) - 3} more)"

        except Exception as exc:
            status = "failed"
            message = str(exc)
            logger.exception("download failed", extra={"collector_fields": {
                "provider": self.provider.name, "symbol": symbol,
                "timeframe": timeframe.value, "error": message,
            }})
            raise
        finally:
            duration_ms = (time.perf_counter() - t0) * 1000
            log_collection(
                logger,
                provider=self.provider.name,
                symbol=symbol,
                timeframe=timeframe.value,
                duration_ms=duration_ms,
                rows_imported=rows_imported,
                rows_rejected=rows_rejected,
                job_type=job_type.value,
            )
            self.database.log_collection(CollectionLogEntry(
                provider=self.provider.name,
                symbol=symbol,
                timeframe=timeframe.value,
                job_type=job_type.value,
                duration_ms=duration_ms,
                rows_imported=rows_imported,
                rows_rejected=rows_rejected,
                status=status,
                message=message,
            ))

        return rows_imported, rows_rejected

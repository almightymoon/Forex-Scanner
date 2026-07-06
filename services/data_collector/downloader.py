"""Download historical and incremental data from providers."""

import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from services.data_collector.database import CollectorDatabase
from services.data_collector.gap_detection import GapDetectionEngine
from services.data_collector.logger import get_logger, log_collection
from services.data_collector.metrics import get_collector_metrics
from services.data_collector.models import CollectionLogEntry, JobType
from services.data_collector.normalizer import DataNormalizer
from services.data_collector.provider_sync import ProviderSynchronizer
from services.data_collector.providers.base_provider import BaseDataProvider
from services.data_collector.repair import RepairEngine
from services.data_collector.validator import DataValidator
from shared.types.models import Timeframe

logger = get_logger("downloader")


class DataDownloader:
    """Orchestrates provider download → normalize → validate → persist → gap repair."""

    def __init__(
        self,
        provider: BaseDataProvider,
        database: CollectorDatabase,
        validator: Optional[DataValidator] = None,
        repair_engine: Optional[RepairEngine] = None,
    ):
        self.provider = provider
        self.database = database
        self.validator = validator or DataValidator()
        self.normalizer = DataNormalizer(provider.name)
        self.gap_detector = GapDetectionEngine()
        self.repair = repair_engine or RepairEngine(self.validator)
        self.sync = ProviderSynchronizer(database)
        self.metrics = get_collector_metrics()

    async def download_historical(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> tuple[int, int]:
        return await self._run_download(symbol, timeframe, start, end, JobType.HISTORICAL_IMPORT)

    async def download_incremental(
        self,
        symbol: str,
        timeframe: Timeframe,
        lookback_hours: int = 24,
    ) -> tuple[int, int]:
        end = datetime.now(timezone.utc)
        latest = self.database.get_latest_timestamp(symbol, timeframe)
        if latest:
            start = latest - timedelta(seconds=DataNormalizer.expected_interval_seconds(timeframe))
        else:
            start = end - timedelta(hours=lookback_hours)
        return await self._run_download(symbol, timeframe, start, end, JobType.INCREMENTAL_UPDATE)

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
        rows_repaired = 0
        status = "completed"
        message = ""
        last_candle: Optional[datetime] = None

        try:
            existing = self.database.get_existing_timestamps(symbol, timeframe, start, end)
            raw = await self.provider.download_history(symbol, timeframe, start, end)
            normalized = self.normalizer.normalize_candles(raw)
            result = self.validator.validate_candles(normalized)

            rows_rejected = len(result.rejected)
            if rows_rejected:
                self.metrics.record_validation_failure(rows_rejected)

            new_candles = [c for c in result.valid if c.timestamp not in existing]
            with self.database.transaction():
                rows_imported = self.database.insert_candles_batch(new_candles, skip_existing=True)

            all_candles = self.database.get_candles(symbol, timeframe, limit=5000, since=start)
            gap_report = self.gap_detector.detect(all_candles, symbol, timeframe, provider=self.provider.name)
            if gap_report.gaps:
                self.database.store_gaps(gap_report.gaps)
                self.metrics.record_gaps(len(gap_report.gaps))

            repair_result = await self.repair.repair_gaps(
                self.database.get_open_gaps(symbol, timeframe),
                self.provider,
                self.database,
                metrics=self.metrics,
            )
            rows_repaired = repair_result.repaired

            if all_candles:
                last_candle = all_candles[-1].timestamp

            if result.warnings:
                message = "; ".join(result.warnings[:3])

            duration_ms = (time.perf_counter() - t0) * 1000
            self.metrics.record_import(duration_ms=duration_ms, success=True, rows=rows_imported)
            self.metrics.record_provider_latency(self.provider.name, duration_ms)

            await self.sync.sync_provider(
                self.provider,
                rows_downloaded=rows_imported,
                rows_rejected=rows_rejected,
                rows_repaired=rows_repaired,
                last_candle=last_candle,
            )

        except Exception as exc:
            status = "failed"
            message = str(exc)
            duration_ms = (time.perf_counter() - t0) * 1000
            self.metrics.record_import(duration_ms=duration_ms, success=False)
            await self.sync.sync_provider(
                self.provider,
                rows_downloaded=rows_imported,
                rows_rejected=rows_rejected,
                error=exc,
            )
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

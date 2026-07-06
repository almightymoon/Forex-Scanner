"""Historical Import Manager — range-based imports without re-importing existing candles."""

import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from services.data_collector.config import get_collector_config
from services.data_collector.logger import get_logger
from services.data_collector.models import HistoricalRange, ImportResult
from services.data_collector.normalizer import DataNormalizer
from services.data_collector.providers.base_provider import BaseDataProvider
from services.data_collector.repair import RepairEngine
from services.data_collector.validator import DataValidator
from shared.types.models import Timeframe

logger = get_logger("import_history")

RANGE_DELTAS: dict[HistoricalRange, Optional[timedelta]] = {
    HistoricalRange.ONE_MONTH: timedelta(days=30),
    HistoricalRange.THREE_MONTHS: timedelta(days=91),
    HistoricalRange.SIX_MONTHS: timedelta(days=182),
    HistoricalRange.ONE_YEAR: timedelta(days=365),
    HistoricalRange.FIVE_YEARS: timedelta(days=365 * 5),
    HistoricalRange.MAXIMUM: None,
}


class HistoricalImportManager:
    """Import historical candles incrementally — never re-import existing rows."""

    def __init__(
        self,
        database,
        validator: Optional[DataValidator] = None,
        repair_engine: Optional[RepairEngine] = None,
    ):
        self.database = database
        self.validator = validator or DataValidator()
        self.repair = repair_engine or RepairEngine(self.validator)
        self.config = get_collector_config()

    async def import_range(
        self,
        provider: BaseDataProvider,
        symbol: str,
        timeframe: Timeframe,
        range_label: HistoricalRange | str,
        *,
        end: Optional[datetime] = None,
        metrics=None,
    ) -> ImportResult:
        t0 = time.perf_counter()
        end_ts = end or datetime.now(timezone.utc)
        if isinstance(range_label, str):
            range_label = HistoricalRange(range_label)

        start_ts = self._compute_start(range_label, end_ts)
        result = ImportResult(
            symbol=symbol.upper(),
            timeframe=timeframe,
            range_label=range_label.value,
        )

        try:
            existing = self.database.get_existing_timestamps(symbol, timeframe, start_ts, end_ts)
            raw = await provider.download_history(symbol, timeframe, start_ts, end_ts)
            normalizer = DataNormalizer(provider.name)
            normalized = normalizer.normalize_candles(raw)
            validation = self.validator.validate_candles(normalized)

            new_candles = [c for c in validation.valid if c.timestamp not in existing]
            result.rows_skipped = len(validation.valid) - len(new_candles)
            result.rows_rejected = len(validation.rejected)

            if new_candles:
                with self.database.transaction():
                    result.rows_imported = self.database.insert_candles_batch(
                        new_candles, skip_existing=True,
                    )

            all_candles = self.database.get_candles(symbol, timeframe, limit=10_000, since=start_ts)
            repair_result = await self.repair.repair_series(
                symbol, timeframe, all_candles, provider, self.database, metrics=metrics,
            )
            result.gaps_repaired = repair_result.repaired

            self.database.log_import_job(
                symbol, timeframe, range_label.value, start_ts, end_ts,
                result.rows_imported, result.status,
            )

        except Exception as exc:
            result.status = "failed"
            result.message = str(exc)
            logger.error(
                "historical import failed",
                extra={"collector_fields": {
                    "symbol": symbol, "timeframe": timeframe.value,
                    "range": range_label.value, "error": str(exc),
                }},
            )
            if metrics:
                metrics.record_import(duration_ms=(time.perf_counter() - t0) * 1000, success=False)

        result.duration_ms = (time.perf_counter() - t0) * 1000
        if metrics and result.status == "completed":
            metrics.record_import(duration_ms=result.duration_ms, success=True, rows=result.rows_imported)
        return result

    async def import_incremental(
        self,
        provider: BaseDataProvider,
        symbol: str,
        timeframe: Timeframe,
        *,
        lookback_hours: int = 24,
        metrics=None,
    ) -> ImportResult:
        end_ts = datetime.now(timezone.utc)
        latest = self.database.get_latest_timestamp(symbol, timeframe)
        if latest:
            start_ts = latest - timedelta(seconds=DataNormalizer.expected_interval_seconds(timeframe))
        else:
            start_ts = end_ts - timedelta(hours=lookback_hours)

        return await self._import_window(
            provider, symbol, timeframe, start_ts, end_ts, "incremental", metrics=metrics,
        )

    async def _import_window(
        self,
        provider: BaseDataProvider,
        symbol: str,
        timeframe: Timeframe,
        start_ts: datetime,
        end_ts: datetime,
        label: str,
        *,
        metrics=None,
    ) -> ImportResult:
        t0 = time.perf_counter()
        result = ImportResult(symbol=symbol.upper(), timeframe=timeframe, range_label=label)

        existing = self.database.get_existing_timestamps(symbol, timeframe, start_ts, end_ts)
        raw = await provider.download_history(symbol, timeframe, start_ts, end_ts)
        normalizer = DataNormalizer(provider.name)
        normalized = normalizer.normalize_candles(raw)
        validation = self.validator.validate_candles(normalized)

        new_candles = [c for c in validation.valid if c.timestamp not in existing]
        result.rows_skipped = len(validation.valid) - len(new_candles)
        result.rows_rejected = len(validation.rejected)

        if new_candles:
            with self.database.transaction():
                result.rows_imported = self.database.insert_candles_batch(new_candles, skip_existing=True)

        result.duration_ms = (time.perf_counter() - t0) * 1000
        if metrics:
            metrics.record_import(duration_ms=result.duration_ms, success=True, rows=result.rows_imported)
        return result

    @staticmethod
    def _compute_start(range_label: HistoricalRange, end: datetime) -> datetime:
        delta = RANGE_DELTAS.get(range_label)
        if delta is None:
            return end - timedelta(days=365 * 10)
        return end - delta

"""Automatic Data Repair Engine — recover missing candles from providers."""

from datetime import datetime, timedelta, timezone

from services.data_collector.gap_detection import GapDetectionEngine
from services.data_collector.logger import get_logger
from services.data_collector.models import DataGap, GapStatus, GapType, RepairResult
from services.data_collector.normalizer import DataNormalizer
from services.data_collector.providers.base_provider import BaseDataProvider
from services.data_collector.validator import DataValidator
from shared.types.models import Timeframe

logger = get_logger("repair")


class RepairEngine:
    """
    Attempt recovery when gaps are detected.

    Never silently ignores missing data — unresolved gaps are persisted.
    """

    def __init__(self, validator: DataValidator | None = None):
        self.validator = validator or DataValidator()
        self.gap_detector = GapDetectionEngine()

    async def repair_gaps(
        self,
        gaps: list[DataGap],
        provider: BaseDataProvider,
        database,
        *,
        metrics=None,
    ) -> RepairResult:
        result = RepairResult()
        interval_cache: dict[str, int] = {}

        for gap in gaps:
            if gap.gap_type == GapType.DUPLICATE:
                continue

            result.attempted += 1
            tf = gap.timeframe
            interval = interval_cache.get(tf.value) or DataNormalizer.expected_interval_seconds(tf)
            interval_cache[tf.value] = interval

            start, end = self._repair_window(gap, interval)
            try:
                raw = await provider.download_history(gap.symbol, tf, start, end)
                normalizer = DataNormalizer(provider.name)
                normalized = normalizer.normalize_candles(raw)
                validation = self.validator.validate_candles(normalized, detect_gaps=False)

                existing = database.get_existing_timestamps(
                    gap.symbol, tf, start, end,
                )
                new_candles = [
                    c for c in validation.valid
                    if c.timestamp not in existing
                ]

                if new_candles:
                    inserted = database.insert_candles_batch(new_candles, skip_existing=True)
                    result.rows_inserted += inserted

                if gap.expected_timestamp and any(
                    c.timestamp == gap.expected_timestamp for c in validation.valid
                ):
                    database.update_gap_status(gap, GapStatus.REPAIRED)
                    result.repaired += 1
                    if metrics:
                        metrics.record_repair(success=True)
                elif new_candles:
                    database.update_gap_status(gap, GapStatus.REPAIRED)
                    result.repaired += 1
                    if metrics:
                        metrics.record_repair(success=True)
                else:
                    database.update_gap_status(gap, GapStatus.UNRESOLVED)
                    result.unresolved += 1
                    if metrics:
                        metrics.record_repair(success=False)
                    logger.warning(
                        "gap repair failed — no matching candles",
                        extra={"collector_fields": {
                            "symbol": gap.symbol,
                            "timeframe": tf.value,
                            "expected": gap.expected_timestamp.isoformat() if gap.expected_timestamp else None,
                        }},
                    )

            except Exception as exc:
                database.update_gap_status(gap, GapStatus.UNRESOLVED)
                result.unresolved += 1
                if metrics:
                    metrics.record_repair(success=False)
                logger.error(
                    "gap repair error",
                    extra={"collector_fields": {
                        "symbol": gap.symbol,
                        "timeframe": tf.value,
                        "error": str(exc),
                    }},
                )

        return result

    async def repair_series(
        self,
        symbol: str,
        timeframe: Timeframe,
        candles: list,
        provider: BaseDataProvider,
        database,
        *,
        metrics=None,
    ) -> RepairResult:
        """Detect gaps in a series, persist them, then attempt repair."""
        report = self.gap_detector.detect(candles, symbol, timeframe, provider=provider.name)
        repairable = [
            g for g in report.gaps
            if g.gap_type in (GapType.MISSING, GapType.TIMESTAMP_GAP)
        ]
        if report.gaps:
            database.store_gaps(report.gaps)
        if not repairable:
            return RepairResult()
        stored = database.get_open_gaps(symbol, timeframe)
        return await self.repair_gaps(stored or repairable, provider, database, metrics=metrics)

    @staticmethod
    def _repair_window(gap: DataGap, interval: int) -> tuple[datetime, datetime]:
        if gap.expected_timestamp:
            start = gap.expected_timestamp - timedelta(seconds=interval)
            end = gap.expected_timestamp + timedelta(seconds=interval)
            return start, end
        start = gap.gap_start or datetime.now(timezone.utc) - timedelta(hours=1)
        end = gap.gap_end or datetime.now(timezone.utc)
        return start, end

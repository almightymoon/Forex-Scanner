"""Gap Detection Engine — find missing, duplicate, overlapping, and out-of-order candles."""

from datetime import datetime, timedelta, timezone

from services.data_collector.models import DataGap, GapReport, GapStatus, GapType
from services.data_collector.normalizer import DataNormalizer
from shared.types.models import Timeframe


class GapDetectionEngine:
    """Detect data quality issues in a candle series and produce storable gap records."""

    def detect(
        self,
        candles: list,
        symbol: str,
        timeframe: Timeframe,
        *,
        provider: str = "",
    ) -> GapReport:
        if not candles:
            return GapReport(gaps=[])

        interval = DataNormalizer.expected_interval_seconds(timeframe)
        tolerance = timedelta(seconds=interval * 0.5)

        gaps: list[DataGap] = []
        duplicates = out_of_order = overlaps = missing = 0
        seen: dict[datetime, int] = {}

        # Detect out-of-order in original sequence
        for i in range(1, len(candles)):
            if self._ts(candles[i]) < self._ts(candles[i - 1]):
                out_of_order += 1
                gaps.append(DataGap(
                    symbol=symbol,
                    timeframe=timeframe,
                    gap_type=GapType.OUT_OF_ORDER,
                    expected_timestamp=self._ts(candles[i - 1]) + timedelta(seconds=interval),
                    gap_start=self._ts(candles[i - 1]),
                    gap_end=self._ts(candles[i]),
                    status=GapStatus.OPEN,
                    provider=provider,
                ))

        sorted_candles = sorted(candles, key=lambda c: self._ts(c))

        for i, candle in enumerate(sorted_candles):
            ts = self._ts(candle)

            if ts in seen:
                duplicates += 1
                gaps.append(DataGap(
                    symbol=symbol,
                    timeframe=timeframe,
                    gap_type=GapType.DUPLICATE,
                    expected_timestamp=ts,
                    gap_start=ts,
                    gap_end=ts,
                    status=GapStatus.OPEN,
                    provider=provider,
                ))
                seen[ts] += 1
                continue
            seen[ts] = 1

            if i > 0:
                prev_ts = self._ts(sorted_candles[i - 1])
                if ts < prev_ts:
                    continue  # already flagged in original-order pass

                delta = ts - prev_ts
                if delta < tolerance and delta.total_seconds() > 0:
                    overlaps += 1
                    gaps.append(DataGap(
                        symbol=symbol,
                        timeframe=timeframe,
                        gap_type=GapType.OVERLAP,
                        expected_timestamp=prev_ts + timedelta(seconds=interval),
                        gap_start=prev_ts,
                        gap_end=ts,
                        status=GapStatus.OPEN,
                        provider=provider,
                    ))
                    continue

                if delta.total_seconds() > interval * 1.5:
                    missing_count = int(delta.total_seconds() // interval) - 1
                    missing += missing_count
                    expected = prev_ts + timedelta(seconds=interval)
                    while expected < ts - tolerance:
                        gaps.append(DataGap(
                            symbol=symbol,
                            timeframe=timeframe,
                            gap_type=GapType.MISSING,
                            expected_timestamp=expected,
                            gap_start=prev_ts,
                            gap_end=ts,
                            status=GapStatus.OPEN,
                            provider=provider,
                        ))
                        expected += timedelta(seconds=interval)

                    gaps.append(DataGap(
                        symbol=symbol,
                        timeframe=timeframe,
                        gap_type=GapType.TIMESTAMP_GAP,
                        expected_timestamp=expected,
                        gap_start=prev_ts,
                        gap_end=ts,
                        status=GapStatus.OPEN,
                        provider=provider,
                    ))

        return GapReport(
            gaps=gaps,
            duplicates=duplicates,
            out_of_order=out_of_order,
            overlaps=overlaps,
            missing=missing,
        )

    def detect_missing_in_range(
        self,
        existing_timestamps: set[datetime],
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
        *,
        provider: str = "",
    ) -> GapReport:
        """Detect missing expected slots between start and end given known timestamps."""
        interval = DataNormalizer.expected_interval_seconds(timeframe)
        gaps: list[DataGap] = []
        missing = 0

        current = start if start.tzinfo else start.replace(tzinfo=timezone.utc)
        end_ts = end if end.tzinfo else end.replace(tzinfo=timezone.utc)

        while current <= end_ts:
            if current not in existing_timestamps:
                missing += 1
                gaps.append(DataGap(
                    symbol=symbol,
                    timeframe=timeframe,
                    gap_type=GapType.MISSING,
                    expected_timestamp=current,
                    gap_start=current - timedelta(seconds=interval),
                    gap_end=current + timedelta(seconds=interval),
                    status=GapStatus.OPEN,
                    provider=provider,
                ))
            current += timedelta(seconds=interval)

        return GapReport(gaps=gaps, missing=missing)

    @staticmethod
    def _ts(candle) -> datetime:
        ts = candle.timestamp if hasattr(candle, "timestamp") else candle
        if ts.tzinfo is None:
            return ts.replace(tzinfo=timezone.utc)
        return ts.astimezone(timezone.utc)

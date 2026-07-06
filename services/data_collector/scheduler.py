"""Job scheduler for the market data collector — scheduling logic only (no cron)."""

import asyncio
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Callable, Coroutine, Optional

from services.data_collector.config import get_collector_config
from services.data_collector.logger import get_logger
from services.data_collector.models import CollectionJob, JobStatus, JobType
from shared.types.models import Timeframe

logger = get_logger("scheduler")

JobHandler = Callable[[CollectionJob], Coroutine[None, None, None]]


class CollectionScheduler:
    """
    Manages historical imports, incremental updates, and live polling jobs.

    Supports retry of failed jobs and concurrency limits. Does not implement
    cron — callers invoke tick() or run_pending() on their own schedule.
    """

    def __init__(
        self,
        handler: Optional[JobHandler] = None,
        max_concurrent: Optional[int] = None,
        retry_count: Optional[int] = None,
        retry_backoff_seconds: Optional[int] = None,
    ):
        cfg = get_collector_config().scheduler
        self.max_concurrent = max_concurrent if max_concurrent is not None else cfg.max_concurrent_jobs
        self.retry_count = retry_count if retry_count is not None else cfg.retry_count
        self.retry_backoff = (
            retry_backoff_seconds if retry_backoff_seconds is not None else cfg.retry_backoff_seconds
        )
        self._handler = handler
        self._pending: deque[CollectionJob] = deque()
        self._running: dict[str, CollectionJob] = {}
        self._completed: list[CollectionJob] = []
        self._failed: list[CollectionJob] = []

    def schedule_historical(
        self,
        provider: str,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> CollectionJob:
        job = CollectionJob(
            id=str(uuid.uuid4()),
            job_type=JobType.HISTORICAL_IMPORT,
            provider=provider,
            symbol=symbol,
            timeframe=timeframe,
            start_time=start,
            end_time=end,
        )
        self._pending.append(job)
        return job

    def schedule_incremental(
        self, provider: str, symbol: str, timeframe: Timeframe
    ) -> CollectionJob:
        job = CollectionJob(
            id=str(uuid.uuid4()),
            job_type=JobType.INCREMENTAL_UPDATE,
            provider=provider,
            symbol=symbol,
            timeframe=timeframe,
        )
        self._pending.append(job)
        return job

    def schedule_live_poll(
        self, provider: str, symbols: list[str]
    ) -> list[CollectionJob]:
        jobs = []
        for symbol in symbols:
            job = CollectionJob(
                id=str(uuid.uuid4()),
                job_type=JobType.LIVE_POLL,
                provider=provider,
                symbol=symbol,
                timeframe=Timeframe.M1,
            )
            self._pending.append(job)
            jobs.append(job)
        return jobs

    def schedule_full_matrix(
        self,
        provider: str,
        symbols: tuple[str, ...],
        timeframes: tuple[str, ...],
        job_type: JobType = JobType.INCREMENTAL_UPDATE,
    ) -> list[CollectionJob]:
        """Enqueue one job per symbol × timeframe combination."""
        jobs = []
        for symbol in symbols:
            for tf_str in timeframes:
                tf = Timeframe(tf_str)
                if job_type == JobType.INCREMENTAL_UPDATE:
                    jobs.append(self.schedule_incremental(provider, symbol, tf))
                else:
                    now = datetime.now(timezone.utc)
                    jobs.append(self.schedule_historical(
                        provider, symbol, tf,
                        start=now.replace(year=now.year - 1),
                        end=now,
                    ))
        return jobs

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    @property
    def running_count(self) -> int:
        return len(self._running)

    def get_queue_snapshot(self) -> dict[str, int]:
        return {
            "pending": len(self._pending),
            "running": len(self._running),
            "completed": len(self._completed),
            "failed": len(self._failed),
        }

    async def run_pending(self) -> int:
        """Process pending jobs up to concurrency limit. Returns jobs started."""
        started = 0
        while self._pending and len(self._running) < self.max_concurrent:
            job = self._pending.popleft()
            job.status = JobStatus.RUNNING
            self._running[job.id] = job
            started += 1
            asyncio.create_task(self._execute(job))
        return started

    async def _execute(self, job: CollectionJob) -> None:
        try:
            if self._handler:
                await self._handler(job)
            job.status = JobStatus.COMPLETED
            self._completed.append(job)
        except Exception as exc:
            job.error = str(exc)
            if job.retry_count < self.retry_count:
                job.retry_count += 1
                job.status = JobStatus.RETRYING
                logger.warning(
                    "job retry scheduled",
                    extra={"collector_fields": {
                        "job_id": job.id, "attempt": job.retry_count,
                        "symbol": job.symbol, "error": job.error,
                    }},
                )
                await asyncio.sleep(self.retry_backoff * job.retry_count)
                self._pending.appendleft(job)
            else:
                job.status = JobStatus.FAILED
                self._failed.append(job)
                logger.error(
                    "job failed permanently",
                    extra={"collector_fields": {
                        "job_id": job.id, "symbol": job.symbol, "error": job.error,
                    }},
                )
        finally:
            self._running.pop(job.id, None)

    async def drain(self) -> None:
        """Run all pending jobs to completion."""
        while self._pending or self._running:
            await self.run_pending()
            if self._running:
                await asyncio.sleep(0.1)

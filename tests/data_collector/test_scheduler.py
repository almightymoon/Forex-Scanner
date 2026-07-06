"""Unit tests for the collection scheduler."""

import asyncio
import unittest
from unittest.mock import AsyncMock

from services.data_collector.models import JobStatus, JobType
from services.data_collector.scheduler import CollectionScheduler
from shared.types.models import Timeframe


class TestScheduler(unittest.TestCase):
    def test_schedule_incremental(self):
        sched = CollectionScheduler()
        job = sched.schedule_incremental("mock", "EURUSD", Timeframe.H1)
        self.assertEqual(job.job_type, JobType.INCREMENTAL_UPDATE)
        self.assertEqual(sched.pending_count, 1)

    def test_schedule_full_matrix(self):
        sched = CollectionScheduler()
        jobs = sched.schedule_full_matrix(
            "mock", ("EURUSD", "GBPUSD"), ("H1", "H4")
        )
        self.assertEqual(len(jobs), 4)
        self.assertEqual(sched.pending_count, 4)

    def test_retry_on_failure(self):
        handler = AsyncMock(side_effect=RuntimeError("provider down"))
        sched = CollectionScheduler(handler=handler, retry_count=2, retry_backoff_seconds=0)
        sched.schedule_incremental("mock", "EURUSD", Timeframe.H1)

        async def run():
            await sched.run_pending()
            await sched.drain()

        asyncio.run(run())
        self.assertEqual(len(sched._failed), 1)
        self.assertEqual(sched._failed[0].status, JobStatus.FAILED)
        self.assertEqual(sched._failed[0].retry_count, 2)

    def test_successful_job_completes(self):
        handler = AsyncMock()
        sched = CollectionScheduler(handler=handler)
        job = sched.schedule_incremental("mock", "EURUSD", Timeframe.H1)

        async def run():
            await sched.run_pending()
            await sched.drain()

        asyncio.run(run())
        self.assertEqual(job.status, JobStatus.COMPLETED)
        self.assertEqual(len(sched._completed), 1)


if __name__ == "__main__":
    unittest.main()

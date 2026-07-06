"""Collector daemon — scheduled incremental imports and gap repair."""

import asyncio
import logging
import os
import signal

from services.data_collector.collector import DataCollector
from services.data_collector.config import get_collector_config
from services.data_collector.logger import get_logger

logger = get_logger("daemon")


class CollectorDaemon:
    """Run incremental collection on a polling interval."""

    def __init__(self, collector: DataCollector | None = None):
        self.collector = collector or DataCollector()
        self.config = get_collector_config()
        self._running = False

    def _active_provider(self) -> str | None:
        if self.config.providers.mt5.enabled:
            return "mt5"
        if self.config.providers.dukascopy.enabled:
            return "dukascopy"
        return None

    async def start(self) -> None:
        await self.collector.initialize()
        self._running = True
        interval = self.config.scheduler.polling_interval_seconds
        provider = self._active_provider()

        if not provider:
            logger.warning(
                "no collector provider enabled — set providers.mt5.enabled or "
                "providers.dukascopy.enabled in config/data_collector.yaml"
            )
            return

        logger.info(
            "collector daemon started",
            extra={"collector_fields": {
                "provider": provider,
                "interval_seconds": interval,
                "symbols": len(self.config.symbols),
            }},
        )

        while self._running:
            try:
                self.collector.schedule_incremental_matrix(provider)
                await self.collector.drain_jobs()
                logger.info(
                    "collection cycle complete",
                    extra={"collector_fields": {"provider": provider}},
                )
            except Exception as exc:
                logger.error(
                    "collection cycle failed",
                    extra={"collector_fields": {"error": str(exc)}},
                )
            await asyncio.sleep(interval)

    async def stop(self) -> None:
        self._running = False
        await self.collector.shutdown()


async def run_daemon() -> None:
    daemon = CollectorDaemon()
    loop = asyncio.get_running_loop()

    def _shutdown(*_args):
        logger.info("shutdown signal received")
        asyncio.create_task(daemon.stop())

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _shutdown)
        except NotImplementedError:
            pass

    try:
        await daemon.start()
    finally:
        await daemon.stop()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    if os.getenv("COLLECTOR_DAEMON_ENABLED", "true").lower() != "true":
        logger.info("collector daemon disabled (COLLECTOR_DAEMON_ENABLED=false)")
        return
    asyncio.run(run_daemon())


if __name__ == "__main__":
    main()

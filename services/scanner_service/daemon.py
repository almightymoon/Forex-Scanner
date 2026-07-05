"""Continuous scanner daemon — runs 24/7 in the background."""

import asyncio
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from services.scanner_service.pipeline import ScannerPipeline
from shared.configs.settings import get_settings

settings = get_settings()


class ScannerDaemon:
    def __init__(self, interval: int | None = None, min_score: int | None = None):
        self.interval = interval or settings.SCAN_INTERVAL_SECONDS
        self.min_score = min_score or settings.MIN_ALERT_SCORE
        self.pipeline = ScannerPipeline()
        self._running = False

    async def start(self):
        self._running = True
        print(f"[DAEMON] FX Navigators Scanner started")
        print(f"[DAEMON] Interval: {self.interval}s | Alert threshold: {self.min_score}+")
        print(f"[DAEMON] Press Ctrl+C to stop\n")

        while self._running:
            try:
                ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
                signals = await self.pipeline.scan_all(
                    min_score=60,
                    alert_threshold=self.min_score,
                )
                strong = [s for s in signals if s.score >= self.min_score]
                print(f"[{ts}] Scanned {len(signals)} signals | {len(strong)} above {self.min_score}")
                for s in strong[:3]:
                    print(f"  ★ {s.symbol} {s.direction.value.upper()} {s.score}/100")
            except Exception as e:
                print(f"[DAEMON ERROR] {e}")

            await asyncio.sleep(self.interval)

    def stop(self):
        self._running = False
        print("\n[DAEMON] Stopped.")


async def main():
    daemon = ScannerDaemon()
    loop = asyncio.get_event_loop()

    def handle_signal():
        daemon.stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, handle_signal)

    await daemon.start()


if __name__ == "__main__":
    asyncio.run(main())

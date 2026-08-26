"""Aggregated dashboard data — one request for the entire UI."""

import asyncio
import time
from datetime import datetime, timezone

from services.market_data_service.provider import FOREX_PAIRS, METAL_PAIRS
from services.scanner_service.scanner_service import ScannerService
from shared.types.models import Timeframe, to_dict

# Serve a recent scan immediately; refresh in the background when stale.
_CACHE_TTL_SEC = 45.0
# Full 28-pair scans are too slow for interactive loads — majors + metals first.
_DEFAULT_DASHBOARD_SYMBOLS = list(dict.fromkeys([*FOREX_PAIRS[:7], *METAL_PAIRS]))


class DashboardService:
    def __init__(self, scanner: ScannerService | None = None):
        self.scanner = scanner or ScannerService()
        self._cache: dict | None = None
        self._cache_at: float = 0.0
        self._scan_lock = asyncio.Lock()
        self._scan_task: asyncio.Task | None = None

    async def get_dashboard(
        self,
        min_score: int = 60,
        timeframe: Timeframe = Timeframe.H1,
        symbols: list[str] | None = None,
        signal_limit: int = 30,
    ) -> dict:
        scan_symbols = symbols or _DEFAULT_DASHBOARD_SYMBOLS
        now = time.monotonic()
        if self._cache is not None and (now - self._cache_at) < _CACHE_TTL_SEC:
            return self._cache

        # If a scan is already running, return last good payload (or DB cache)
        # so the UI stays responsive instead of stacking multi-minute scans.
        if self._scan_lock.locked():
            if self._cache is not None:
                return self._cache
            db_fallback = self._from_db(min_score=min_score, signal_limit=signal_limit)
            if db_fallback is not None:
                return db_fallback

        async with self._scan_lock:
            now = time.monotonic()
            if self._cache is not None and (now - self._cache_at) < _CACHE_TTL_SEC:
                return self._cache

            payload = await self._scan(
                min_score=min_score,
                timeframe=timeframe,
                symbols=scan_symbols,
                signal_limit=signal_limit,
            )
            self._cache = payload
            self._cache_at = time.monotonic()
            return payload

    async def _scan(
        self,
        min_score: int,
        timeframe: Timeframe,
        symbols: list[str] | None,
        signal_limit: int,
    ) -> dict:
        signals_raw = await self.scanner.pipeline.scan_all(
            symbols=symbols or _DEFAULT_DASHBOARD_SYMBOLS,
            timeframe=timeframe,
            min_score=min_score,
        )
        try:
            events = await self.scanner.get_calendar()
        except Exception:
            events = []
        stats = self.scanner.get_stats()
        try:
            market_status = await self.scanner.get_market_status()
        except Exception:
            market_status = {"live": False, "pairs_with_prices": 0, "source": "unknown"}

        heatmap = [
            {
                "symbol": s.symbol,
                "score": s.score,
                "direction": s.direction.value,
                "trend": s.trend.value,
            }
            for s in signals_raw
        ]

        return {
            "stats": stats,
            "signals": [to_dict(s) for s in signals_raw[:signal_limit]],
            "calendar": events,
            "heatmap": heatmap,
            "market_status": market_status,
            "count": len(signals_raw),
            "scanned_at": datetime.now(timezone.utc).isoformat(),
        }

    def _from_db(self, min_score: int, signal_limit: int) -> dict | None:
        try:
            rows = self.scanner.pipeline.db.get_recent_results(
                limit=signal_limit, min_score=min_score
            )
        except Exception:
            return None
        if not rows:
            return None
        heatmap = [
            {
                "symbol": r.get("symbol"),
                "score": r.get("score", 0),
                "direction": r.get("direction"),
                "trend": r.get("trend"),
            }
            for r in rows
        ]
        return {
            "stats": self.scanner.get_stats(),
            "signals": rows[:signal_limit],
            "calendar": [],
            "heatmap": heatmap,
            "market_status": {"live": False, "pairs_with_prices": 0, "source": "cache"},
            "count": len(rows),
            "scanned_at": datetime.now(timezone.utc).isoformat(),
        }

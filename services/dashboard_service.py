"""Aggregated dashboard data — one request for the entire UI."""

from datetime import datetime, timezone

from services.scanner_service.scanner_service import ScannerService
from shared.types.models import Timeframe, to_dict


class DashboardService:
    def __init__(self, scanner: ScannerService | None = None):
        self.scanner = scanner or ScannerService()

    async def get_dashboard(
        self,
        min_score: int = 60,
        timeframe: Timeframe = Timeframe.H1,
        symbols: list[str] | None = None,
        signal_limit: int = 30,
    ) -> dict:
        signals_raw = await self.scanner.pipeline.scan_all(
            symbols=symbols, timeframe=timeframe, min_score=min_score
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
            {"symbol": s.symbol, "score": s.score, "direction": s.direction.value, "trend": s.trend.value}
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

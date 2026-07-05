"""Scanner service facade — business logic entry point for the API."""

from datetime import datetime, timezone

from services.scanner_service.pipeline import ScannerPipeline
from shared.types.models import ScannerSignal, Timeframe, to_dict


class ScannerService:
    """Thin facade over the scanner pipeline for API routes."""

    def __init__(self, pipeline: ScannerPipeline | None = None):
        self.pipeline = pipeline or ScannerPipeline()

    async def scan_live(
        self,
        min_score: int = 60,
        timeframe: Timeframe = Timeframe.H1,
        symbols: list[str] | None = None,
        limit: int = 20,
    ) -> dict:
        signals = await self.pipeline.scan_all(
            symbols=symbols, timeframe=timeframe, min_score=min_score
        )
        return {
            "signals": [to_dict(s) for s in signals[:limit]],
            "count": len(signals),
            "scanned_at": datetime.now(timezone.utc).isoformat(),
        }

    async def scan_symbol(
        self, symbol: str, timeframe: Timeframe = Timeframe.H1, with_ai: bool = True
    ) -> ScannerSignal | None:
        return await self.pipeline.scan_symbol(symbol.upper(), timeframe, with_ai=with_ai)

    async def get_heatmap(
        self,
        timeframe: Timeframe = Timeframe.H1,
        symbols: list[str] | None = None,
    ) -> list[dict]:
        signals = await self.pipeline.scan_all(
            symbols=symbols, timeframe=timeframe, min_score=0, save=False, alert_threshold=100
        )
        return [
            {"symbol": s.symbol, "score": s.score, "direction": s.direction.value, "trend": s.trend.value}
            for s in signals
        ]

    def get_stats(self) -> dict:
        return self.pipeline.db.get_stats()

    async def get_calendar(self) -> list[dict]:
        events = await self.pipeline.news_service.get_events()
        self.pipeline.db.save_economic_events(events)
        return events

    async def get_market_status(self) -> dict:
        prices = {}
        if hasattr(self.pipeline.market_data, "get_live_prices"):
            prices = await self.pipeline.market_data.get_live_prices()
        return {
            "live": len(prices) > 0,
            "pairs_with_prices": len(prices),
            "source": "frankfurter" if prices else "simulated",
        }

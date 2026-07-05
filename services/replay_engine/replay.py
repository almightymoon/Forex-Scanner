"""Historical market replay — candle-by-candle scanner playback."""

from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone

from services.indicator_service.indicators import compute_all
from services.market_data_service.factory import create_market_data_provider
from services.scanner_service.decision_engine import DecisionEngine
from services.smc_service.smc import SMCEngine
from shared.types.models import ScannerSignal, Timeframe, to_dict


SESSION_WINDOWS = {
    "asia": (time(0, 0), time(8, 0)),
    "london": (time(8, 0), time(16, 0)),
    "new_york": (time(13, 0), time(21, 0)),
    "full": (time(0, 0), time(23, 59)),
}


@dataclass
class ReplayFrame:
    index: int
    timestamp: str
    candle: dict
    signal: dict | None = None


@dataclass
class ReplaySession:
    symbol: str
    timeframe: Timeframe
    date: str
    session: str
    frames: list[ReplayFrame] = field(default_factory=list)
    total_candles: int = 0


class ReplayEngine:
    """Replays history and runs the decision engine at each candle."""

    def __init__(self, market_data=None, decision_engine=None, smc_engine=None):
        self.market_data = market_data or create_market_data_provider()
        self.decision_engine = decision_engine or DecisionEngine()
        self.smc_engine = smc_engine or SMCEngine()

    async def build_session(
        self,
        symbol: str,
        date: str,
        timeframe: Timeframe = Timeframe.H1,
        session: str = "london",
        min_window: int = 50,
    ) -> ReplaySession:
        start, end = _session_bounds(date, session)
        candles = await self.market_data.get_historical_candles(
            symbol.upper(), timeframe, start, end
        )
        if len(candles) < min_window:
            all_candles = await self.market_data.get_candles(symbol.upper(), timeframe, 200)
            candles = [c for c in all_candles if start <= c.timestamp <= end] or all_candles

        frames: list[ReplayFrame] = []
        for i in range(min_window, len(candles)):
            window = candles[: i + 1]
            indicators = compute_all(window, symbol.upper(), timeframe)
            smc_patterns = self.smc_engine.detect_all(window, symbol.upper(), timeframe)
            signal: ScannerSignal = self.decision_engine.evaluate(
                symbol.upper(),
                timeframe,
                window,
                indicators,
                smc_patterns,
            )
            c = candles[i]
            frames.append(
                ReplayFrame(
                    index=i,
                    timestamp=c.timestamp.isoformat(),
                    candle={
                        "open": c.open,
                        "high": c.high,
                        "low": c.low,
                        "close": c.close,
                        "volume": c.volume,
                    },
                    signal=to_dict(signal) if signal.score >= 60 else None,
                )
            )

        return ReplaySession(
            symbol=symbol.upper(),
            timeframe=timeframe,
            date=date,
            session=session,
            frames=frames,
            total_candles=len(candles),
        )

    def session_to_dict(self, session: ReplaySession) -> dict:
        setups = [f for f in session.frames if f.signal]
        return {
            "symbol": session.symbol,
            "timeframe": session.timeframe.value,
            "date": session.date,
            "session": session.session,
            "total_candles": session.total_candles,
            "frames": [
                {
                    "index": f.index,
                    "timestamp": f.timestamp,
                    "candle": f.candle,
                    "signal": f.signal,
                }
                for f in session.frames
            ],
            "setup_count": len(setups),
        }


def _session_bounds(date: str, session: str) -> tuple[datetime, datetime]:
    day = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    start_t, end_t = SESSION_WINDOWS.get(session, SESSION_WINDOWS["london"])
    start = datetime.combine(day.date(), start_t, tzinfo=timezone.utc)
    end = datetime.combine(day.date(), end_t, tzinfo=timezone.utc)
    if end <= start:
        end += timedelta(days=1)
    return start, end

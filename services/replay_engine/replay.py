"""Historical market replay — candle-by-candle scanner playback."""

from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone

from services.market_data_service.factory import create_market_data_provider
from services.quant_engine.pipeline import ANALYSIS_PIPELINE_VERSION, analyze_candle_window
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
    analytical_fingerprint: dict | None = None


@dataclass
class ReplaySession:
    symbol: str
    timeframe: Timeframe
    date: str
    session: str
    frames: list[ReplayFrame] = field(default_factory=list)
    total_candles: int = 0
    pipeline_version: str = ANALYSIS_PIPELINE_VERSION


class ReplayEngine:
    """Replays history via the canonical analysis pipeline."""

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
            bundle = analyze_candle_window(
                symbol.upper(),
                timeframe,
                window,
                decision_engine=self.decision_engine,
                smc_engine=self.smc_engine,
                evaluate=True,
            )
            signal: ScannerSignal | None = bundle.signal
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
                    signal=to_dict(signal) if signal and signal.score >= 60 else None,
                    analytical_fingerprint=bundle.analytical_fingerprint(),
                )
            )

        return ReplaySession(
            symbol=symbol.upper(),
            timeframe=timeframe,
            date=date,
            session=session,
            frames=frames,
            total_candles=len(candles),
            pipeline_version=ANALYSIS_PIPELINE_VERSION,
        )

    def session_to_dict(self, session: ReplaySession) -> dict:
        setups = [f for f in session.frames if f.signal]
        return {
            "symbol": session.symbol,
            "timeframe": session.timeframe.value,
            "date": session.date,
            "session": session.session,
            "total_candles": session.total_candles,
            "pipeline_version": session.pipeline_version,
            "frames": [
                {
                    "index": f.index,
                    "timestamp": f.timestamp,
                    "candle": f.candle,
                    "signal": f.signal,
                    "analytical_fingerprint": f.analytical_fingerprint,
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

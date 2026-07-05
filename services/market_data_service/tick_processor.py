"""Process ticks into OHLCV candles."""

from datetime import datetime, timedelta, timezone
from typing import Optional

from shared.types.models import Candle, Tick, Timeframe

from .candle_builder import TF_MINUTES


class TickProcessor:
    """Aggregates ticks into candles for a given timeframe."""

    def __init__(self, timeframe: Timeframe):
        self.timeframe = timeframe
        self._minutes = TF_MINUTES.get(timeframe, 60)
        self._current: dict[str, Candle] = {}
        self._bar_start: dict[str, datetime] = {}

    def _bar_open_time(self, ts: datetime) -> datetime:
        ts = ts.astimezone(timezone.utc)
        minute = (ts.minute // self._minutes) * self._minutes if self._minutes < 1440 else 0
        return ts.replace(minute=minute, second=0, microsecond=0)

    def process_tick(self, tick: Tick) -> Optional[Candle]:
        """Returns a completed candle when a new bar opens, else None."""
        symbol = tick.symbol
        mid = (tick.bid + tick.ask) / 2
        bar_start = self._bar_open_time(tick.timestamp)

        if symbol not in self._current or self._bar_start.get(symbol) != bar_start:
            completed = self._current.get(symbol)
            self._bar_start[symbol] = bar_start
            self._current[symbol] = Candle(
                symbol=symbol,
                timeframe=self.timeframe,
                timestamp=bar_start,
                open=mid,
                high=mid,
                low=mid,
                close=mid,
                volume=tick.volume or 1,
                spread=tick.ask - tick.bid,
            )
            return completed

        candle = self._current[symbol]
        candle.high = max(candle.high, mid)
        candle.low = min(candle.low, mid)
        candle.close = mid
        candle.volume += tick.volume or 1
        return None

    def flush(self, symbol: str) -> Optional[Candle]:
        return self._current.pop(symbol, None)

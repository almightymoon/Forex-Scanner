"""Candle storage — in-memory with optional DB persistence hook."""

from shared.types.models import Candle, Timeframe


class CandleStorage:
    """Stores historical candles keyed by symbol + timeframe."""

    def __init__(self):
        self._candles: dict[str, list[Candle]] = {}

    def _key(self, symbol: str, timeframe: Timeframe) -> str:
        return f"{symbol}_{timeframe.value}"

    def get(self, symbol: str, timeframe: Timeframe) -> list[Candle] | None:
        candles = self._candles.get(self._key(symbol, timeframe))
        return list(candles) if candles else None

    def save(self, symbol: str, timeframe: Timeframe, candles: list[Candle]) -> None:
        self._candles[self._key(symbol, timeframe)] = list(candles)

    def append(self, symbol: str, timeframe: Timeframe, candle: Candle) -> None:
        key = self._key(symbol, timeframe)
        if key not in self._candles:
            self._candles[key] = []
        self._candles[key].append(candle)

    def symbols(self) -> list[str]:
        return list({k.split("_")[0] for k in self._candles})

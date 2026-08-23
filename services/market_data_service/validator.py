"""Market data validation — reject bad ticks and candles before they reach the scanner."""

from shared.market_data.ohlc_integrity import validate_candle_series, validate_ohlc_values
from shared.types.models import Candle, Tick


class DataValidator:
    def validate_tick(self, tick: Tick) -> bool:
        if tick.bid <= 0 or tick.ask <= 0:
            return False
        if tick.ask < tick.bid:
            return False
        spread = tick.ask - tick.bid
        if spread / tick.bid > 0.05:
            return False
        return True

    def validate_candle(self, candle: Candle) -> bool:
        return validate_ohlc_values(candle) is None

    def validate_candles(self, candles: list[Candle]) -> list[Candle]:
        """Return valid candles only. Gaps are not filled; duplicates are dropped."""
        return validate_candle_series(candles, detect_gaps=True, reject_duplicates=True).valid

    def filter_ticks(self, ticks: list[Tick]) -> list[Tick]:
        return [t for t in ticks if self.validate_tick(t)]

    def inspect_candles(self, candles: list[Candle]):
        """Full integrity report including explicit gap metadata."""
        return validate_candle_series(candles, detect_gaps=True, reject_duplicates=True)

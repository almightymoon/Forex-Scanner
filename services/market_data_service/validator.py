"""Market data validation — reject bad ticks and candles before they reach the scanner."""

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
        if candle.high < candle.low:
            return False
        if candle.open < candle.low or candle.open > candle.high:
            return False
        if candle.close < candle.low or candle.close > candle.high:
            return False
        if candle.high <= 0 or candle.low <= 0:
            return False
        return True

    def validate_candles(self, candles: list[Candle]) -> list[Candle]:
        return [c for c in candles if self.validate_candle(c)]

    def filter_ticks(self, ticks: list[Tick]) -> list[Tick]:
        return [t for t in ticks if self.validate_tick(t)]

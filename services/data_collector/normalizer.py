"""Normalize provider output into canonical CollectedCandle / CollectedTick models."""

from datetime import datetime, timezone
from typing import Union

from services.data_collector.models import CollectedCandle, CollectedTick, RawCandle, RawTick
from services.data_collector.symbols import SymbolRegistry
from shared.types.models import Timeframe

TF_SECONDS: dict[str, int] = {
    "M1": 60,
    "M5": 300,
    "M15": 900,
    "M30": 1800,
    "H1": 3600,
    "H4": 14400,
    "D1": 86400,
}


class DataNormalizer:
    """Convert provider-specific formats into the canonical collector model."""

    def __init__(self, provider: str, registry: SymbolRegistry | None = None):
        self.provider = provider
        self.registry = registry or SymbolRegistry()

    def normalize_candle(self, raw: RawCandle) -> CollectedCandle:
        symbol = self.registry.normalize(raw.symbol)
        tf = self._parse_timeframe(raw.timeframe)
        ts = self._normalize_timestamp(raw.timestamp)

        return CollectedCandle(
            symbol=symbol,
            timeframe=tf,
            timestamp=ts,
            open=float(raw.open),
            high=float(raw.high),
            low=float(raw.low),
            close=float(raw.close),
            volume=int(raw.volume or 0),
            provider=self.provider,
            created_at=datetime.now(timezone.utc),
        )

    def normalize_candles(self, raws: list[RawCandle]) -> list[CollectedCandle]:
        return [self.normalize_candle(r) for r in raws]

    def normalize_tick(self, raw: RawTick) -> CollectedTick:
        return CollectedTick(
            symbol=self.registry.normalize(raw.symbol),
            timestamp=self._normalize_timestamp(raw.timestamp),
            bid=float(raw.bid),
            ask=float(raw.ask),
            volume=int(raw.volume or 0),
            provider=self.provider,
            created_at=datetime.now(timezone.utc),
        )

    def normalize_ticks(self, raws: list[RawTick]) -> list[CollectedTick]:
        return [self.normalize_tick(r) for r in raws]

    def _parse_timeframe(self, tf: Union[str, Timeframe]) -> Timeframe:
        if isinstance(tf, Timeframe):
            return tf
        value = str(tf).upper()
        if value not in Timeframe.__members__:
            raise ValueError(f"Unsupported timeframe: {tf}")
        return Timeframe(value)

    def _normalize_timestamp(self, ts: datetime) -> datetime:
        if ts.tzinfo is None:
            return ts.replace(tzinfo=timezone.utc)
        return ts.astimezone(timezone.utc)

    @staticmethod
    def expected_interval_seconds(timeframe: Timeframe) -> int:
        return TF_SECONDS[timeframe.value]

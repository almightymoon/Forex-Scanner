"""Dukascopy bi5 tick file parser."""

import lzma
import struct
from datetime import datetime, timedelta, timezone
from typing import Iterator

# Pip/point size per instrument for Dukascopy integer prices
POINT_VALUES: dict[str, float] = {
    "EURUSD": 0.00001,
    "GBPJPY": 0.001,
    "EURJPY": 0.001,
    "EURGBP": 0.00001,
    "USDJPY": 0.001,
    "USDCHF": 0.00001,
    "AUDUSD": 0.00001,
    "USDCAD": 0.00001,
    "NZDUSD": 0.00001,
    "XAUUSD": 0.01,
    "XAGUSD": 0.001,
    "BTCUSD": 0.01,
    "ETHUSD": 0.01,
}


def point_value(symbol: str) -> float:
    sym = symbol.upper().replace("/", "")
    if sym in POINT_VALUES:
        return POINT_VALUES[sym]
    if "JPY" in sym:
        return 0.001
    if sym.startswith("XAU") or sym.startswith("XAG"):
        return 0.01
    return 0.00001


def parse_bi5_ticks(data: bytes, hour_start: datetime, symbol: str) -> list[tuple[datetime, float, float, float]]:
    """Parse lzma-compressed bi5 tick data into (timestamp, bid, ask, volume) tuples."""
    if not data:
        return []
    try:
        raw = lzma.decompress(data)
    except lzma.LZMAError:
        return []

    pv = point_value(symbol)
    ticks: list[tuple[datetime, float, float, float]] = []
    base = hour_start if hour_start.tzinfo else hour_start.replace(tzinfo=timezone.utc)

    for offset in range(0, len(raw) - 19, 20):
        chunk = raw[offset:offset + 20]
        if len(chunk) < 20:
            break
        ms, ask_i, bid_i, ask_vol, bid_vol = struct.unpack(">IIIff", chunk)
        ts = base + timedelta(milliseconds=ms)
        ask = ask_i * pv
        bid = bid_i * pv
        vol = int(ask_vol + bid_vol)
        ticks.append((ts, bid, ask, float(vol)))
    return ticks


def ticks_to_candles(
    ticks: list[tuple[datetime, float, float, float]],
    interval_seconds: int,
    symbol: str = "EURUSD",
) -> list[dict]:
    """Aggregate ticks into OHLC candles via deterministic BarBuilder."""
    from shared.types.models import Timeframe
    from services.bar_builder.builder import BarBuilder
    from services.bar_builder.constants import TF_SECONDS

    if not ticks:
        return []

    tf = next((t for t, s in TF_SECONDS.items() if s == interval_seconds), Timeframe.M1)
    builder = BarBuilder(symbol, tf)
    bars = builder.from_ticks(ticks)
    return [
        {
            "timestamp": b.candle.timestamp,
            "open": b.candle.open,
            "high": b.candle.high,
            "low": b.candle.low,
            "close": b.candle.close,
            "volume": b.candle.volume,
        }
        for b in bars
    ]

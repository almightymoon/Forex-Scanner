"""Build OHLCV candles from price series or anchor to live spot."""

import random
from datetime import datetime, timedelta, timezone

from shared.types.models import Candle, Timeframe

TF_MINUTES = {
    Timeframe.M1: 1,
    Timeframe.M5: 5,
    Timeframe.M15: 15,
    Timeframe.M30: 30,
    Timeframe.H1: 60,
    Timeframe.H4: 240,
    Timeframe.D1: 1440,
}


def volatility_for_symbol(symbol: str, anchor: float) -> float:
    if symbol.startswith("XAU") or symbol.startswith("XAG"):
        return anchor * 0.002
    if "JPY" in symbol:
        return anchor * 0.0005
    return anchor * 0.0008


def generate_candles(
    symbol: str,
    timeframe: Timeframe,
    count: int,
    start_price: float,
    anchor_price: float | None = None,
) -> list[Candle]:
    """Generate synthetic OHLCV history, optionally snapping the last bar to anchor."""
    minutes = TF_MINUTES.get(timeframe, 60)
    now = datetime.now(timezone.utc)
    candles: list[Candle] = []
    price = start_price
    vol = volatility_for_symbol(symbol, anchor_price or start_price)

    for i in range(count, 0, -1):
        ts = now - timedelta(minutes=minutes * i)
        change = random.gauss(0, vol)
        open_p = price
        close_p = price + change
        high_p = max(open_p, close_p) + abs(random.gauss(0, vol * 0.5))
        low_p = min(open_p, close_p) - abs(random.gauss(0, vol * 0.5))
        volume = random.randint(100, 5000)

        candles.append(
            Candle(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=ts,
                open=round(open_p, 5),
                high=round(high_p, 5),
                low=round(low_p, 5),
                close=round(close_p, 5),
                volume=volume,
                tick_volume=volume * 3,
                spread=0.00015,
            )
        )
        price = close_p

    if anchor_price is not None and candles:
        last = candles[-1]
        candles[-1] = Candle(
            symbol=last.symbol,
            timeframe=last.timeframe,
            timestamp=last.timestamp,
            open=last.open,
            high=max(last.high, anchor_price),
            low=min(last.low, anchor_price),
            close=round(anchor_price, 5),
            volume=last.volume,
            tick_volume=last.tick_volume,
            spread=last.spread,
        )

    return candles


def update_last_candle(candle: Candle, live_price: float) -> Candle:
    return Candle(
        symbol=candle.symbol,
        timeframe=candle.timeframe,
        timestamp=candle.timestamp,
        open=candle.open,
        high=max(candle.high, live_price),
        low=min(candle.low, live_price),
        close=round(live_price, 5),
        volume=candle.volume,
        tick_volume=candle.tick_volume,
        spread=candle.spread,
    )

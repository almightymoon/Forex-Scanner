"""Deterministic synthetic structure scenarios (confirmed swings + candles).

These fixtures do not run the swing engine — they supply hand-built causal
confirmed swings so Market Structure Engine behavior is tested in isolation.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from shared.types.models import Candle, Timeframe
from swing_engine.models import (
    DetectedSwing,
    SwingDirection,
    SwingScope,
    SwingTier,
)


def _ts(index: int) -> datetime:
    return datetime(2024, 3, 4, tzinfo=timezone.utc) + timedelta(hours=index)


def candle(
    index: int,
    *,
    high: float,
    low: float,
    close: float,
    open_: float | None = None,
    symbol: str = "EURUSD",
    timeframe: Timeframe = Timeframe.H1,
) -> Candle:
    open_price = open_ if open_ is not None else (high + low) / 2.0
    return Candle(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=_ts(index),
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=100.0,
    )


def swing(
    pivot: int,
    direction: SwingDirection,
    price: float,
    *,
    confirmation: int | None = None,
    tier: SwingTier = SwingTier.MAJOR,
    scope: SwingScope = SwingScope.EXTERNAL,
) -> DetectedSwing:
    conf = confirmation if confirmation is not None else pivot + 1
    return DetectedSwing(
        timestamp=_ts(pivot),
        price=price,
        direction=direction,
        tier=tier,
        scope=scope,
        pivot_index=pivot,
        confirmed=True,
        confirmed_timestamp=_ts(conf),
        confirmation_index=conf,
        confirmation_delay=max(0, conf - pivot),
        strength=4,
    )


def flat_candles(n: int, *, base: float = 1.1000, symbol: str = "EURUSD") -> list[Candle]:
    out: list[Candle] = []
    for i in range(n):
        out.append(
            candle(
                i,
                high=base + 0.0010,
                low=base - 0.0010,
                close=base,
                symbol=symbol,
            )
        )
    return out


def bullish_structure_scenario() -> tuple[list[Candle], list[DetectedSwing]]:
    """HL + HH after a bullish BOS through the first structural high.

    Timeline:
      L@10=1.1000 (conf 12)
      H@18=1.1200 (conf 20)
      bar 24 close 1.1220 → bullish BOS (neutral→BOS)
      L@28=1.1050 (conf 30) → HL
      H@34=1.1300 (conf 36) → HH
    """
    candles = flat_candles(40, base=1.1100)
    candles[10] = candle(10, high=1.1010, low=1.0990, close=1.1000)
    candles[18] = candle(18, high=1.1210, low=1.1180, close=1.1200)
    candles[24] = candle(24, high=1.1240, low=1.1180, close=1.1220)
    candles[28] = candle(28, high=1.1070, low=1.1040, close=1.1050)
    candles[34] = candle(34, high=1.1310, low=1.1280, close=1.1300)

    swings = [
        swing(10, SwingDirection.LOW, 1.1000, confirmation=12),
        swing(18, SwingDirection.HIGH, 1.1200, confirmation=20),
        swing(28, SwingDirection.LOW, 1.1050, confirmation=30),
        swing(34, SwingDirection.HIGH, 1.1300, confirmation=36),
    ]
    return candles, swings


def bearish_structure_scenario() -> tuple[list[Candle], list[DetectedSwing]]:
    """LH + LL after a bearish BOS through the first structural low."""
    candles = flat_candles(40, base=1.1100)
    candles[10] = candle(10, high=1.1210, low=1.1180, close=1.1200)
    candles[18] = candle(18, high=1.1010, low=1.0990, close=1.1000)
    candles[24] = candle(24, high=1.1020, low=1.0960, close=1.0980)  # break low
    candles[28] = candle(28, high=1.1160, low=1.1130, close=1.1150)  # LH
    candles[34] = candle(34, high=1.0960, low=1.0930, close=1.0950)  # LL

    swings = [
        swing(10, SwingDirection.HIGH, 1.1200, confirmation=12),
        swing(18, SwingDirection.LOW, 1.1000, confirmation=20),
        swing(28, SwingDirection.HIGH, 1.1150, confirmation=30),
        swing(34, SwingDirection.LOW, 1.0950, confirmation=36),
    ]
    return candles, swings


def reversal_choch_scenario() -> tuple[list[Candle], list[DetectedSwing]]:
    """Bullish BOS then break of last HL → bearish CHOCH (pending)."""
    candles = flat_candles(42, base=1.1100)
    candles[10] = candle(10, high=1.1010, low=1.0990, close=1.1000)
    candles[18] = candle(18, high=1.1210, low=1.1180, close=1.1200)
    candles[24] = candle(24, high=1.1240, low=1.1180, close=1.1220)  # BOS↑
    candles[28] = candle(28, high=1.1070, low=1.1040, close=1.1050)  # HL
    candles[34] = candle(34, high=1.1060, low=1.1000, close=1.1020)  # break HL → CHOCH↓

    swings = [
        swing(10, SwingDirection.LOW, 1.1000, confirmation=12),
        swing(18, SwingDirection.HIGH, 1.1200, confirmation=20),
        swing(28, SwingDirection.LOW, 1.1050, confirmation=30),
    ]
    return candles, swings


def ranging_mixed_scenario() -> tuple[list[Candle], list[DetectedSwing]]:
    """Mixed HH/LH and HL/LL without a structural break event."""
    candles = flat_candles(35, base=1.1100)
    candles[8] = candle(8, high=1.1010, low=1.0990, close=1.1000)
    candles[14] = candle(14, high=1.1210, low=1.1180, close=1.1200)
    candles[20] = candle(20, high=1.1060, low=1.1030, close=1.1050)  # HL
    candles[26] = candle(26, high=1.1180, low=1.1150, close=1.1170)  # LH

    swings = [
        swing(8, SwingDirection.LOW, 1.1000, confirmation=10),
        swing(14, SwingDirection.HIGH, 1.1200, confirmation=16),
        swing(20, SwingDirection.LOW, 1.1050, confirmation=22),
        swing(26, SwingDirection.HIGH, 1.1170, confirmation=28),
    ]
    return candles, swings


def equal_high_scenario() -> tuple[list[Candle], list[DetectedSwing]]:
    candles = flat_candles(25, base=1.1100)
    candles[8] = candle(8, high=1.1205, low=1.1180, close=1.1200)
    candles[16] = candle(16, high=1.1205, low=1.1180, close=1.1200)
    swings = [
        swing(8, SwingDirection.HIGH, 1.1200, confirmation=10),
        swing(16, SwingDirection.HIGH, 1.1200, confirmation=18),
    ]
    return candles, swings

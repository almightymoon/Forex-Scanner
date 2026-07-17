import math
from datetime import datetime, timedelta, timezone

from shared.types.models import Candle, Timeframe
from swing_engine.benchmark_sampling import select_calibration_windows


def _long_history(count: int = 7200) -> list[Candle]:
    start = datetime(2022, 1, 1, tzinfo=timezone.utc)
    bars = []
    price = 1800.0
    for index in range(count):
        segment = (index // 900) % 6
        if segment == 0:
            drift, amplitude = 0.16, 0.8
        elif segment == 1:
            drift, amplitude = -0.17, 0.9
        elif segment == 2:
            drift, amplitude = 0.0, 0.35
        elif segment == 3:
            drift, amplitude = 0.04, 3.0
        elif segment == 4:
            drift, amplitude = 0.01, 0.15
        else:
            drift = 0.20 if index % 900 < 450 else -0.23
            amplitude = 1.1
        move = drift + amplitude * math.sin(index / 9.0) * 0.15
        open_ = price
        close = price + move
        high = max(open_, close) + amplitude * 0.2
        low = min(open_, close) - amplitude * 0.2
        bars.append(
            Candle(
                symbol="XAUUSD",
                timeframe=Timeframe.H1,
                timestamp=start + timedelta(hours=index),
                open=open_,
                high=high,
                low=low,
                close=close,
            )
        )
        price = close
    return bars


def test_selects_balanced_non_overlapping_calibration_pack():
    windows = select_calibration_windows(
        _long_history(),
        symbol="XAUUSD",
        timeframe="H1",
        stride=48,
        per_regime=2,
    )
    assert len(windows) == 12
    assert len({window.primary_regime for window in windows}) == 6
    ordered = sorted(windows, key=lambda window: window.source_start_index)
    for left, right in zip(ordered, ordered[1:]):
        assert left.source_end_index + 50 < right.source_start_index
    assert all(window.labelable_start_index == 50 for window in windows)
    assert all(window.labelable_end_index == 349 for window in windows)

"""ATR, pip helpers, and structured logging."""

from __future__ import annotations

import logging
from typing import Any

from shared.types.models import Candle

from swing_engine.config import SwingEngineConfig

logger = logging.getLogger("fxnav.swing_engine")


def pip_size_for_symbol(symbol: str, config: SwingEngineConfig) -> float:
    sym = symbol.upper().replace("/", "")
    overrides = getattr(config.pip_size, "symbol_overrides", {}) or {}
    if sym in overrides:
        return overrides[sym]
    if sym in config.pip_size.jpy_symbols or sym.endswith("JPY"):
        return config.pip_size.jpy
    return config.pip_size.default


def pips_to_price(pips: float, symbol: str, config: SwingEngineConfig) -> float:
    return pips * pip_size_for_symbol(symbol, config)


def compute_atr_series(candles: list[Candle], period: int) -> list[float]:
    """Wilder ATR — O(n)."""
    n = len(candles)
    if n == 0:
        return []
    trs: list[float] = [candles[0].high - candles[0].low]
    for i in range(1, n):
        c, prev = candles[i], candles[i - 1]
        tr = max(c.high - c.low, abs(c.high - prev.close), abs(c.low - prev.close))
        trs.append(tr)

    atrs: list[float] = [trs[0]]
    for i in range(1, n):
        if i < period:
            atrs.append(sum(trs[: i + 1]) / (i + 1))
        elif i == period:
            atrs.append(sum(trs[1 : period + 1]) / period)
        else:
            atrs.append((atrs[-1] * (period - 1) + trs[i]) / period)
    return atrs


def atr_at(index: int, atr_series: list[float], candles: list[Candle]) -> float:
    if 0 <= index < len(atr_series) and atr_series[index] > 0:
        return atr_series[index]
    if candles and 0 <= index < len(candles):
        return max(candles[index].high - candles[index].low, 1e-12)
    return 1e-12


def log_stage(stage: str, input_count: int, output_count: int, **details: Any) -> None:
    logger.info(
        "swing_engine.%s",
        stage,
        extra={
            "stage": stage,
            "input_count": input_count,
            "output_count": output_count,
            "rejected": input_count - output_count,
            **details,
        },
    )

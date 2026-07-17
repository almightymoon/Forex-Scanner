"""Deterministic regime sampling for human swing-annotation packs."""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import Iterable

from shared.types.models import Candle


@dataclass(frozen=True)
class BenchmarkWindow:
    sample_id: str
    source_start_index: int
    source_end_index: int
    labelable_start_index: int
    labelable_end_index: int
    split: str
    primary_regime: str
    regime_tags: tuple[str, ...] = ()
    features: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "sample_id": self.sample_id,
            "source_start_index": self.source_start_index,
            "source_end_index": self.source_end_index,
            "labelable_start_index": self.labelable_start_index,
            "labelable_end_index": self.labelable_end_index,
            "split": self.split,
            "primary_regime": self.primary_regime,
            "regime_tags": list(self.regime_tags),
            "features": {key: round(value, 6) for key, value in self.features.items()},
        }


@dataclass(frozen=True)
class _Candidate:
    start: int
    end: int
    features: dict[str, float]


def _true_ranges(candles: list[Candle]) -> list[float]:
    ranges: list[float] = []
    previous_close = candles[0].close
    for candle in candles:
        ranges.append(
            max(
                candle.high - candle.low,
                abs(candle.high - previous_close),
                abs(candle.low - previous_close),
            )
        )
        previous_close = candle.close
    return ranges


def _features(window: list[Candle]) -> dict[str, float]:
    closes = [bar.close for bar in window]
    returns = [b - a for a, b in zip(closes, closes[1:])]
    true_ranges = _true_ranges(window)
    atr = statistics.median(true_ranges) or 1e-12
    median_price = statistics.median(closes) or 1e-12
    total_path = sum(abs(value) for value in returns) or 1e-12
    net_move = closes[-1] - closes[0]
    efficiency = abs(net_move) / total_path
    half = len(closes) // 2
    first_return = closes[half] - closes[0]
    second_return = closes[-1] - closes[half]
    reversal = (
        (abs(first_return) + abs(second_return)) / atr
        if first_return * second_return < 0
        else 0.0
    )
    wick_sweeps = 0
    lookback = 20
    for index in range(lookback, len(window)):
        bar = window[index]
        prior_high = max(item.high for item in window[index - lookback : index])
        prior_low = min(item.low for item in window[index - lookback : index])
        if bar.high > prior_high and bar.close < prior_high:
            wick_sweeps += 1
        if bar.low < prior_low and bar.close > prior_low:
            wick_sweeps += 1
    return {
        "atr": atr,
        "volatility_ratio": atr / median_price,
        "efficiency_ratio": min(1.0, efficiency),
        "net_move_atr": net_move / atr,
        "absolute_move_atr": abs(net_move) / atr,
        "reversal_score": reversal,
        "liquidity_sweeps": float(wick_sweeps),
        "range_atr": (max(bar.high for bar in window) - min(bar.low for bar in window)) / atr,
    }


def _overlaps(candidate: _Candidate, selected: Iterable[_Candidate], buffer_bars: int) -> bool:
    for item in selected:
        if candidate.start <= item.end + buffer_bars and candidate.end >= item.start - buffer_bars:
            return True
    return False


def select_calibration_windows(
    candles: list[Candle],
    *,
    symbol: str,
    timeframe: str,
    window_size: int = 400,
    left_context: int = 50,
    right_context: int = 50,
    stride: int = 48,
    per_regime: int = 2,
    split: str = "TRAIN",
) -> list[BenchmarkWindow]:
    """Select a balanced, non-overlapping 12-window calibration pack.

    The sampler only proposes charts.  Regime tags are selection metadata and
    must not be treated as human swing truth.
    """
    if left_context + right_context >= window_size:
        raise ValueError("context consumes the complete window")
    required = window_size * 3
    if len(candles) < required:
        raise ValueError(
            f"Need at least {required} candles for a balanced pack; received {len(candles)}"
        )

    candidates: list[_Candidate] = []
    for start in range(0, len(candles) - window_size + 1, stride):
        end = start + window_size - 1
        candidates.append(_Candidate(start=start, end=end, features=_features(candles[start : end + 1])))

    regimes = (
        "STRONG_BULLISH_TREND",
        "STRONG_BEARISH_TREND",
        "RANGE",
        "HIGH_VOLATILITY",
        "LOW_VOLATILITY",
        "TREND_REVERSAL",
    )

    volatility_values = sorted(item.features["volatility_ratio"] for item in candidates)
    low_cut = volatility_values[max(0, math.floor(0.20 * (len(volatility_values) - 1)))]
    high_cut = volatility_values[min(len(volatility_values) - 1, math.ceil(0.80 * (len(volatility_values) - 1)))]

    def score(item: _Candidate, regime: str) -> float:
        f = item.features
        if regime == "STRONG_BULLISH_TREND":
            return f["net_move_atr"] + 12.0 * f["efficiency_ratio"]
        if regime == "STRONG_BEARISH_TREND":
            return -f["net_move_atr"] + 12.0 * f["efficiency_ratio"]
        if regime == "RANGE":
            return 12.0 * (1.0 - f["efficiency_ratio"]) - 0.15 * f["absolute_move_atr"]
        if regime == "HIGH_VOLATILITY":
            return 1_000_000.0 * f["volatility_ratio"] + f["liquidity_sweeps"]
        if regime == "LOW_VOLATILITY":
            return -1_000_000.0 * f["volatility_ratio"] + (1.0 - f["efficiency_ratio"])
        return f["reversal_score"] + 0.5 * f["liquidity_sweeps"]

    def eligible(item: _Candidate, regime: str) -> bool:
        f = item.features
        if regime == "STRONG_BULLISH_TREND":
            return f["net_move_atr"] > 0 and f["efficiency_ratio"] >= 0.12
        if regime == "STRONG_BEARISH_TREND":
            return f["net_move_atr"] < 0 and f["efficiency_ratio"] >= 0.12
        if regime == "RANGE":
            return f["efficiency_ratio"] <= 0.18
        if regime == "HIGH_VOLATILITY":
            return f["volatility_ratio"] >= high_cut
        if regime == "LOW_VOLATILITY":
            return f["volatility_ratio"] <= low_cut
        return f["reversal_score"] > 0

    selected: list[tuple[str, _Candidate]] = []
    selected_candidates: list[_Candidate] = []
    buffer_bars = right_context
    for regime in regimes:
        ranked = sorted(
            (item for item in candidates if eligible(item, regime)),
            key=lambda item: score(item, regime),
            reverse=True,
        )
        picked = 0
        for item in ranked:
            if _overlaps(item, selected_candidates, buffer_bars):
                continue
            selected.append((regime, item))
            selected_candidates.append(item)
            picked += 1
            if picked == per_regime:
                break
        if picked < per_regime:
            # Relax only the regime threshold, never the non-overlap rule.
            for item in sorted(candidates, key=lambda candidate: score(candidate, regime), reverse=True):
                if _overlaps(item, selected_candidates, buffer_bars):
                    continue
                selected.append((regime, item))
                selected_candidates.append(item)
                picked += 1
                if picked == per_regime:
                    break
        if picked < per_regime:
            raise ValueError(f"Could not find {per_regime} non-overlapping {regime} windows")

    selected.sort(key=lambda pair: pair[1].start)
    result: list[BenchmarkWindow] = []
    for number, (regime, item) in enumerate(selected, start=1):
        tags = [regime]
        if item.features["liquidity_sweeps"] >= 2:
            tags.append("LIQUIDITY_SWEEP_CANDIDATE")
        if item.features["reversal_score"] > 8:
            tags.append("REVERSAL_CANDIDATE")
        sample_id = f"{symbol.upper()}_{timeframe}_{number:03d}"
        result.append(
            BenchmarkWindow(
                sample_id=sample_id,
                source_start_index=item.start,
                source_end_index=item.end,
                labelable_start_index=left_context,
                labelable_end_index=window_size - right_context - 1,
                split=split,
                primary_regime=regime,
                regime_tags=tuple(tags),
                features=item.features,
            )
        )
    return result

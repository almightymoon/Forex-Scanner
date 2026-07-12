"""Independent ground-truth pivots for synthetic benchmark series.

Labels use the same fractal pivot definition as the engine (lookback-based local
extrema) but without noise filters, confirmation, or scoring — so benchmarks
measure detection accuracy rather than self-consistency.
"""

from __future__ import annotations

from datetime import datetime

from shared.types.models import Candle

from swing_engine.models import BenchmarkLabel, SwingDirection, SwingScope, SwingTier


def fractal_pivot_indices(
    candles: list[Candle],
    *,
    left: int = 3,
    right: int = 3,
) -> list[tuple[int, SwingDirection]]:
    """Fractal pivot bar indices — independent of engine pipeline stages."""
    out: list[tuple[int, SwingDirection]] = []
    n = len(candles)
    for i in range(left, n - right):
        hi = candles[i].high
        lo = candles[i].low
        is_high = all(hi >= candles[j].high for j in range(i - left, i + right + 1))
        is_low = all(lo <= candles[j].low for j in range(i - left, i + right + 1))
        if is_high and not is_low:
            out.append((i, SwingDirection.HIGH))
        elif is_low and not is_high:
            out.append((i, SwingDirection.LOW))
    return out


def synthetic_pivot_indices(n: int, *, period: int = 12) -> list[tuple[int, SwingDirection]]:
    """Legacy phase-schedule pivots (generator math). Prefer fractal_pivot_indices."""
    half = max(period // 2, 1)
    out: list[tuple[int, SwingDirection]] = []
    for i in range(n):
        phase = i % period
        if phase == half:
            out.append((i, SwingDirection.HIGH))
        elif phase == period - 1:
            out.append((i, SwingDirection.LOW))
    return out


def labels_from_synthetic_bars(
    bars: list[Candle],
    *,
    period: int = 12,
    left: int = 3,
    right: int = 3,
    tier: SwingTier = SwingTier.MAJOR,
    scope: SwingScope = SwingScope.EXTERNAL,
) -> list[BenchmarkLabel]:
    """Build benchmark labels from fractal pivots on bar OHLC."""
    labels: list[BenchmarkLabel] = []
    for idx, direction in fractal_pivot_indices(bars, left=left, right=right):
        bar = bars[idx]
        price = bar.high if direction == SwingDirection.HIGH else bar.low
        labels.append(BenchmarkLabel(
            pivot_index=idx,
            timestamp=bar.timestamp,
            price=price,
            direction=direction,
            tier=tier,
            scope=scope,
        ))
    return labels


def write_ground_truth_file(
    path,
    *,
    bars: list[Candle],
    symbol: str,
    timeframe: str,
    regime: str,
    period: int = 12,
    left: int = 3,
    right: int = 3,
    description: str = "",
) -> int:
    """Write human-review label JSON from fractal pivots."""
    import json
    from pathlib import Path

    labels = labels_from_synthetic_bars(bars, period=period, left=left, right=right)
    payload = {
        "symbol": symbol,
        "timeframe": timeframe,
        "regime": regime,
        "benchmark_version": "2.0",
        "label_source": "fractal_truth",
        "source_engine": "independent",
        "description": description or "Fractal pivots (lookback) — independent of engine pipeline",
        "generated_at": datetime.utcnow().isoformat(timespec="seconds"),
        "swings": [
            {
                "pivot_index": lb.pivot_index,
                "timestamp": lb.timestamp.isoformat(),
                "price": round(lb.price, 6),
                "direction": lb.direction.value,
                "tier": lb.tier.value,
                "scope": lb.scope.value,
            }
            for lb in labels
        ],
    }
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return len(labels)

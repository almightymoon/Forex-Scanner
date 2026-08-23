"""Volatility-aware equality tolerance and high/low clustering."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ClusterConfig:
    atr_fraction: float = 0.15  # cluster radius = max(min_tick, atr_fraction * ATR)
    min_tick: float = 1e-5
    min_touches: int = 2


def equality_tolerance(atr: float, *, config: ClusterConfig | None = None) -> float:
    cfg = config or ClusterConfig()
    atr = max(0.0, float(atr))
    return max(cfg.min_tick, cfg.atr_fraction * atr if atr > 0 else cfg.min_tick)


@dataclass(frozen=True)
class PriceCluster:
    price: float  # mean of members
    indices: tuple[int, ...]
    prices: tuple[float, ...]

    @property
    def touches(self) -> int:
        return len(self.indices)


def cluster_prices(
    indexed_prices: list[tuple[int, float]],
    *,
    tolerance: float,
    min_touches: int = 2,
) -> list[PriceCluster]:
    """Greedy chronological clustering of nearby prices within tolerance."""

    if not indexed_prices:
        return []
    ordered = sorted(indexed_prices, key=lambda x: (x[1], x[0]))
    clusters: list[PriceCluster] = []
    used = [False] * len(ordered)

    for i, (idx, price) in enumerate(ordered):
        if used[i]:
            continue
        members = [(idx, price)]
        used[i] = True
        for j in range(i + 1, len(ordered)):
            if used[j]:
                continue
            j_idx, j_price = ordered[j]
            if abs(j_price - price) <= tolerance or abs(j_price - members[-1][1]) <= tolerance:
                # Also keep cluster centroid check
                centroid = sum(p for _, p in members) / len(members)
                if abs(j_price - centroid) <= tolerance:
                    members.append((j_idx, j_price))
                    used[j] = True
            elif j_price - price > tolerance * 2:
                break
        if len(members) >= min_touches:
            prices = tuple(p for _, p in members)
            indices = tuple(i_ for i_, _ in members)
            clusters.append(
                PriceCluster(
                    price=sum(prices) / len(prices),
                    indices=indices,
                    prices=prices,
                )
            )
    return clusters

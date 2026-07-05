"""Load Decision Engine V2 scoring weights from config/scoring.yaml."""

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "scoring.yaml"


@dataclass(frozen=True)
class V2Weights:
    trend: int = 20
    market_structure: int = 20
    liquidity: int = 10
    order_block: int = 10
    fair_value_gap: int = 10
    momentum: int = 10
    volatility: int = 5
    risk: int = 5
    news: int = 5
    multi_timeframe: int = 5

    def as_dict(self) -> dict[str, int]:
        return {
            "trend": self.trend,
            "market_structure": self.market_structure,
            "liquidity": self.liquidity,
            "order_block": self.order_block,
            "fair_value_gap": self.fair_value_gap,
            "momentum": self.momentum,
            "volatility": self.volatility,
            "risk": self.risk,
            "news": self.news,
            "multi_timeframe": self.multi_timeframe,
        }

    @property
    def total(self) -> int:
        return sum(self.as_dict().values())


@dataclass
class V2ScoringConfig:
    weights: V2Weights = field(default_factory=V2Weights)
    rules: dict[str, dict[str, int]] = field(default_factory=dict)
    thresholds: dict[str, float] = field(default_factory=dict)
    session_weights: dict[str, float] = field(default_factory=dict)


def _load_yaml() -> dict[str, Any]:
    if not _CONFIG_PATH.exists():
        return {}
    with open(_CONFIG_PATH) as f:
        return yaml.safe_load(f) or {}


@lru_cache
def get_v2_scoring_config() -> V2ScoringConfig:
    raw = _load_yaml()
    w = raw.get("weights", {})
    weights = V2Weights(
        trend=int(w.get("trend", 20)),
        market_structure=int(w.get("market_structure", 20)),
        liquidity=int(w.get("liquidity", 10)),
        order_block=int(w.get("order_block", 10)),
        fair_value_gap=int(w.get("fair_value_gap", 10)),
        momentum=int(w.get("momentum", 10)),
        volatility=int(w.get("volatility", 5)),
        risk=int(w.get("risk", 5)),
        news=int(w.get("news", 5)),
        multi_timeframe=int(w.get("multi_timeframe", 5)),
    )
    return V2ScoringConfig(
        weights=weights,
        rules=raw.get("rules", {}),
        thresholds=raw.get("thresholds", {}),
        session_weights=raw.get("session_weights", {}),
    )


def reload_v2_scoring_config() -> V2ScoringConfig:
    get_v2_scoring_config.cache_clear()
    return get_v2_scoring_config()

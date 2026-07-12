"""Configuration loader — all thresholds from config/swing_detection.yaml."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from shared.types.models import Timeframe

_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "swing_detection.yaml"


@dataclass(frozen=True)
class PivotConfig:
    left_lookback: int = 3
    right_lookback: int = 3


@dataclass(frozen=True)
class NoiseFilterConfig:
    min_candle_distance: int = 2
    min_pip_distance: float = 2.0
    min_atr_multiple: float = 0.25
    dedupe_equal_levels: bool = True
    equal_level_tolerance_pips: float = 1.5
    ignore_consecutive_same_direction: bool = True


@dataclass(frozen=True)
class AtrConfig:
    period: int = 14
    validation_multiplier: float = 0.35


@dataclass(frozen=True)
class LegConfig:
    min_pips: float = 2.0
    min_atr_multiple: float = 0.35


@dataclass(frozen=True)
class ConfirmationConfig:
    min_candles: int = 2
    delay_bars: int = 2
    require_structure_break: bool = False
    required_retracement_atr: float = 0.0


@dataclass(frozen=True)
class StrengthConfig:
    weights: dict[str, float] = field(
        default_factory=lambda: {
            "leg_size": 0.25,
            "atr_multiple": 0.25,
            "reaction_size": 0.20,
            "duration": 0.15,
            "volume": 0.15,
        }
    )
    level_thresholds: tuple[int, ...] = (20, 40, 60, 80)


@dataclass(frozen=True)
class ClassificationConfig:
    major_min_atr_multiple: float = 1.2
    major_min_strength: int = 4
    minor_max_atr_multiple: float = 1.2
    external_score_threshold: float = 0.6
    internal_score_threshold: float = -0.25


@dataclass(frozen=True)
class ConfidenceConfig:
    confirmed_bonus: float = 0.15
    unconfirmed_penalty: float = 0.6
    major_multiplier: float = 1.1
    delay_penalty_per_bar: float = 0.02


@dataclass(frozen=True)
class PipSizeConfig:
    default: float = 0.0001
    jpy: float = 0.01
    jpy_symbols: tuple[str, ...] = (
        "USDJPY", "EURJPY", "GBPJPY", "AUDJPY", "NZDJPY", "CADJPY", "CHFJPY",
    )


@dataclass(frozen=True)
class EvaluationConfig:
    price_match_tolerance_pips: float = 2.0
    index_match_tolerance_bars: int = 2


@dataclass(frozen=True)
class SwingEngineConfig:
    pivot: PivotConfig = field(default_factory=PivotConfig)
    noise_filter: NoiseFilterConfig = field(default_factory=NoiseFilterConfig)
    atr: AtrConfig = field(default_factory=AtrConfig)
    leg: LegConfig = field(default_factory=LegConfig)
    confirmation: ConfirmationConfig = field(default_factory=ConfirmationConfig)
    strength: StrengthConfig = field(default_factory=StrengthConfig)
    classification: ClassificationConfig = field(default_factory=ClassificationConfig)
    confidence: ConfidenceConfig = field(default_factory=ConfidenceConfig)
    pip_size: PipSizeConfig = field(default_factory=PipSizeConfig)
    evaluation: EvaluationConfig = field(default_factory=EvaluationConfig)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _dict_to_config(data: dict[str, Any]) -> SwingEngineConfig:
    return SwingEngineConfig(
        pivot=PivotConfig(**data.get("pivot", {})),
        noise_filter=NoiseFilterConfig(**data.get("noise_filter", {})),
        atr=AtrConfig(**data.get("atr", {})),
        leg=LegConfig(**data.get("leg", {})),
        confirmation=ConfirmationConfig(**data.get("confirmation", {})),
        strength=StrengthConfig(
            weights=data.get("strength", {}).get("weights", StrengthConfig().weights),
            level_thresholds=tuple(data.get("strength", {}).get("level_thresholds", (20, 40, 60, 80))),
        ),
        classification=ClassificationConfig(**data.get("classification", {})),
        confidence=ConfidenceConfig(**data.get("confidence", {})),
        pip_size=PipSizeConfig(
            default=data.get("pip_size", {}).get("default", 0.0001),
            jpy=data.get("pip_size", {}).get("jpy", 0.01),
            jpy_symbols=tuple(data.get("pip_size", {}).get("jpy_symbols", PipSizeConfig().jpy_symbols)),
        ),
        evaluation=EvaluationConfig(**data.get("evaluation", {})),
    )


@lru_cache(maxsize=1)
def _load_raw_config() -> dict[str, Any]:
    with _CONFIG_PATH.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def get_config(timeframe: Timeframe | None = None, **overrides: Any) -> SwingEngineConfig:
    """Load config with optional per-timeframe overrides."""
    raw = _load_raw_config()
    base = {k: v for k, v in raw.items() if k != "timeframe_overrides"}
    if timeframe:
        tf_key = timeframe.value
        tf_overrides = raw.get("timeframe_overrides", {}).get(tf_key, {})
        base = _deep_merge(base, tf_overrides)
    base = _deep_merge(base, overrides) if overrides else base
    return _dict_to_config(base)


# Legacy alias
SwingDetectionConfig = SwingEngineConfig
get_swing_detection_config = get_config

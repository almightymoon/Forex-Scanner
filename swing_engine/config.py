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
    allow_equal_levels: bool = False
    equal_level_tolerance_pips: float = 1.5
    min_separation_bars: int = 1
    min_pivot_strength: float = 0.0
    use_body_extreme: bool = False


@dataclass(frozen=True)
class NoiseFilterConfig:
    min_candle_distance: int = 2
    min_pip_distance: float = 2.0
    min_atr_multiple: float = 0.25
    dedupe_equal_levels: bool = True
    equal_level_tolerance_pips: float = 1.5
    ignore_consecutive_same_direction: bool = True
    spread_filter_enabled: bool = False
    max_spread_atr_ratio: float = 0.35
    volatility_filter_enabled: bool = False
    min_volatility_atr: float = 0.15
    consolidation_max_bars: int = 0
    insignificant_pullback_atr: float = 0.0


@dataclass(frozen=True)
class AtrConfig:
    period: int = 14
    validation_multiplier: float = 0.35


@dataclass(frozen=True)
class LegConfig:
    min_pips: float = 2.0
    min_atr_multiple: float = 0.35
    validate_same_direction: bool = False


@dataclass(frozen=True)
class ConfirmationConfig:
    min_candles: int = 2
    delay_bars: int = 2
    require_structure_break: bool = False
    required_retracement_atr: float = 0.0
    displacement_atr_min: float = 0.0
    displacement_bars: int = 1
    break_internal_structure: bool = False


@dataclass(frozen=True)
class StrengthConfig:
    weights: dict[str, float] = field(
        default_factory=lambda: {
            "leg_size": 0.20,
            "atr_multiple": 0.15,
            "reaction_size": 0.15,
            "duration": 0.10,
            "volume": 0.10,
            "wick_ratio": 0.10,
            "displacement": 0.10,
            "trend_quality": 0.10,
        }
    )
    level_thresholds: tuple[int, ...] = (20, 40, 60, 80)
    reaction_bars: int = 4
    duration_cap: int = 20
    leg_atr_divisor: float = 2.5
    atr_divisor: float = 2.0
    reaction_divisor: float = 1.5
    displacement_divisor: float = 2.0
    normalized_max: float = 100.0


@dataclass(frozen=True)
class TierWeights:
    leg_atr: float = 0.35
    strength: float = 0.25
    reaction: float = 0.15
    confirmation: float = 0.15
    duration: float = 0.10


@dataclass(frozen=True)
class ClassificationConfig:
    major_min_atr_multiple: float = 1.2
    major_min_strength: int = 4
    minor_max_atr_multiple: float = 1.2
    external_score_threshold: float = 0.6
    internal_score_threshold: float = -0.25
    protected_lookback_swings: int = 3
    tier_weights: TierWeights = field(default_factory=TierWeights)


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
    min_f1_regression: float = 0.90


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


def _tier_weights(data: dict[str, Any]) -> TierWeights:
    tw = data.get("tier_weights", {})
    return TierWeights(**tw) if tw else TierWeights()


def _dict_to_config(data: dict[str, Any]) -> SwingEngineConfig:
    clf = data.get("classification", {})
    clf_data = {k: v for k, v in clf.items() if k != "tier_weights"}
    clf_data["tier_weights"] = _tier_weights(clf)
    return SwingEngineConfig(
        pivot=PivotConfig(**data.get("pivot", {})),
        noise_filter=NoiseFilterConfig(**data.get("noise_filter", {})),
        atr=AtrConfig(**data.get("atr", {})),
        leg=LegConfig(**data.get("leg", {})),
        confirmation=ConfirmationConfig(**data.get("confirmation", {})),
        strength=StrengthConfig(
            weights=data.get("strength", {}).get("weights", StrengthConfig().weights),
            level_thresholds=tuple(data.get("strength", {}).get("level_thresholds", (20, 40, 60, 80))),
            reaction_bars=data.get("strength", {}).get("reaction_bars", 4),
            duration_cap=data.get("strength", {}).get("duration_cap", 20),
            leg_atr_divisor=data.get("strength", {}).get("leg_atr_divisor", 2.5),
            atr_divisor=data.get("strength", {}).get("atr_divisor", 2.0),
            reaction_divisor=data.get("strength", {}).get("reaction_divisor", 1.5),
            displacement_divisor=data.get("strength", {}).get("displacement_divisor", 2.0),
            normalized_max=data.get("strength", {}).get("normalized_max", 100.0),
        ),
        classification=ClassificationConfig(**clf_data),
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


def get_config(
    timeframe: Timeframe | None = None,
    version: str | None = None,
    **overrides: Any,
) -> SwingEngineConfig:
    """Load config with optional per-timeframe and per-version overrides."""
    raw = _load_raw_config()
    base = {k: v for k, v in raw.items() if k not in ("timeframe_overrides", "version_profiles")}
    if version:
        profile = raw.get("version_profiles", {}).get(version, {})
        base = _deep_merge(base, profile)
    if timeframe:
        tf_key = timeframe.value
        tf_overrides = raw.get("timeframe_overrides", {}).get(tf_key, {})
        base = _deep_merge(base, tf_overrides)
    base = _deep_merge(base, overrides) if overrides else base
    return _dict_to_config(base)


# Legacy alias
SwingDetectionConfig = SwingEngineConfig
get_swing_detection_config = get_config

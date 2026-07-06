"""Swing detection configuration — per-timeframe and sensitivity presets."""

from __future__ import annotations

from dataclasses import dataclass, field, fields, replace
from typing import Any

from shared.types.models import Timeframe


@dataclass(frozen=True)
class NoiseFilterConfig:
    """Sensitivity knobs for noise rejection."""

    enabled: bool = True
    min_atr_multiple: float = 0.35
    equal_level_tolerance_atr: float = 0.15
    max_equal_level_repeats: int = 2
    sideways_range_atr: float = 1.5
    micro_swing_strength: float = 25.0
    sensitivity: float = 1.0  # 0.5 = strict, 1.0 = default, 1.5 = loose


@dataclass(frozen=True)
class SwingConfig:
    """Core swing detector parameters."""

    lookback: int = 3
    confirmation: int = 2
    minimum_strength: float = 30.0
    minimum_distance_atr: float = 0.35
    atr_period: int = 14
    atr_multiplier: float = 1.0
    major_displacement_atr: float = 1.2
    minor_displacement_atr: float = 0.5
    noise_filter: NoiseFilterConfig = field(default_factory=NoiseFilterConfig)
    confirmed_only: bool = False

    def effective_min_distance(self) -> float:
        return self.minimum_distance_atr * self.atr_multiplier

    def effective_major_threshold(self) -> float:
        return self.major_displacement_atr * self.atr_multiplier

    def with_sensitivity(self, sensitivity: float) -> SwingConfig:
        """Return a copy scaled by sensitivity (higher = more swings)."""
        nf = self.noise_filter
        scale = 1.0 / max(sensitivity, 0.1)
        return SwingConfig(
            lookback=max(1, self.lookback),
            confirmation=max(1, self.confirmation),
            minimum_strength=max(0.0, self.minimum_strength * scale),
            minimum_distance_atr=self.minimum_distance_atr * scale,
            atr_period=self.atr_period,
            atr_multiplier=self.atr_multiplier,
            major_displacement_atr=self.major_displacement_atr * scale,
            minor_displacement_atr=self.minor_displacement_atr * scale,
            noise_filter=NoiseFilterConfig(
                enabled=nf.enabled,
                min_atr_multiple=nf.min_atr_multiple * scale,
                equal_level_tolerance_atr=nf.equal_level_tolerance_atr,
                max_equal_level_repeats=nf.max_equal_level_repeats,
                sideways_range_atr=nf.sideways_range_atr,
                micro_swing_strength=nf.micro_swing_strength,
                sensitivity=sensitivity,
            ),
            confirmed_only=self.confirmed_only,
        )


_TIMEFRAME_PRESETS: dict[Timeframe, SwingConfig] = {
    Timeframe.M1: SwingConfig(lookback=2, confirmation=2, minimum_distance_atr=0.25, atr_period=14),
    Timeframe.M5: SwingConfig(lookback=2, confirmation=2, minimum_distance_atr=0.30, atr_period=14),
    Timeframe.M15: SwingConfig(lookback=3, confirmation=2, minimum_distance_atr=0.32, atr_period=14),
    Timeframe.M30: SwingConfig(lookback=3, confirmation=2, minimum_distance_atr=0.34, atr_period=14),
    Timeframe.H1: SwingConfig(lookback=3, confirmation=3, minimum_distance_atr=0.35, atr_period=14),
    Timeframe.H4: SwingConfig(lookback=4, confirmation=3, minimum_distance_atr=0.40, atr_period=14),
    Timeframe.D1: SwingConfig(lookback=5, confirmation=4, minimum_distance_atr=0.50, atr_period=14),
}


def get_swing_config(timeframe: Timeframe | None = None, **overrides: Any) -> SwingConfig:
    """Resolve config for a timeframe with optional overrides."""
    base = _TIMEFRAME_PRESETS.get(timeframe or Timeframe.H1, SwingConfig())
    if not overrides:
        return base

    noise_data = overrides.pop("noise_filter", None)
    valid = {f.name for f in fields(SwingConfig)}
    cfg_overrides = {k: v for k, v in overrides.items() if k in valid}

    cfg = replace(base, **cfg_overrides) if cfg_overrides else base

    if noise_data is not None:
        nf = cfg.noise_filter
        if isinstance(noise_data, NoiseFilterConfig):
            cfg = replace(cfg, noise_filter=noise_data)
        else:
            cfg = replace(cfg, noise_filter=replace(nf, **noise_data))

    return cfg

"""Noise filtering and validation — re-exports core implementation."""

from scanner.swing_detection.filters import (
    apply_noise_filters,
    validate_atr_movement,
    validate_minimum_leg,
)

__all__ = ["apply_noise_filters", "validate_atr_movement", "validate_minimum_leg"]

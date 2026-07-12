"""Shim — use swing_engine.strength."""

from swing_engine.strength import calculate_strength, score_all_swings
from swing_engine.scoring import score_and_classify as classify_swings

__all__ = ["calculate_strength", "score_all_swings", "classify_swings"]

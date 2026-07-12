"""Shim — validation handled in swing_engine pipeline."""

from swing_engine.models import DetectedSwing

def validate_swings(swings: list, **kwargs) -> tuple[bool, list[str]]:
    if not swings:
        return True, []
    indices = [getattr(s, "pivot_index", 0) for s in swings]
    issues = []
    if indices != sorted(indices):
        issues.append("not_chronological")
    return len(issues) == 0, issues

def ensure_alternating(swings: list) -> list:
    return swings

__all__ = ["validate_swings", "ensure_alternating"]

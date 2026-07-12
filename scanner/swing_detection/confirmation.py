"""Shim — use swing_engine.confirmation."""

from swing_engine.confirmation import confirm_swings
from swing_engine.models import InternalSwing as Swing

__all__ = ["confirm_swings", "Swing"]

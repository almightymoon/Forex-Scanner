"""Backward-compatible shim — use services.quant_engine.decision.engine."""

from services.quant_engine.decision.engine import DecisionEngine

__all__ = ["DecisionEngine"]

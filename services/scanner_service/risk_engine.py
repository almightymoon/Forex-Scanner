"""Backward-compatible shim — use services.quant_engine.decision.engines.risk."""

from services.quant_engine.decision.engines.risk import RiskEngine

__all__ = ["RiskEngine"]

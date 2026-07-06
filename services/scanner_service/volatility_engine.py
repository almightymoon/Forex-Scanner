"""Backward-compatible shim — use services.quant_engine.decision.engines.volatility."""

from services.quant_engine.decision.engines.volatility import VolatilityEngine

__all__ = ["VolatilityEngine"]

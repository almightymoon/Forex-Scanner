"""Backward-compatible shim — use services.quant_engine.decision.engines.momentum."""

from services.quant_engine.decision.engines.momentum import MomentumEngine

__all__ = ["MomentumEngine"]

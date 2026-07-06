"""Backward-compatible shim — use services.quant_engine.decision.engines.mtf."""

from services.quant_engine.decision.engines.mtf import MultiTimeframeEngine

__all__ = ["MultiTimeframeEngine"]

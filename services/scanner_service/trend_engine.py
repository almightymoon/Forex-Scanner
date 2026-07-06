"""Backward-compatible shim — use services.quant_engine.trend.engine."""

from services.quant_engine.trend.engine import TrendEngine

__all__ = ["TrendEngine"]

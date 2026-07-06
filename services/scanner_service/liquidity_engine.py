"""Backward-compatible shim — use services.quant_engine.liquidity.engine."""

from services.quant_engine.liquidity.engine import LiquidityEngine

__all__ = ["LiquidityEngine"]

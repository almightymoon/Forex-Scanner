"""Backward-compatible shim — use services.quant_engine.order_blocks.engine."""

from services.quant_engine.order_blocks.engine import OrderBlockEngine

__all__ = ["OrderBlockEngine"]

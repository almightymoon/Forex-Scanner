"""Shim — use swing_engine.visualization."""

from swing_engine.visualization import SwingVisualizer

build_chart_overlay = SwingVisualizer().build
ChartOverlay = dict

__all__ = ["build_chart_overlay", "SwingVisualizer", "ChartOverlay"]

#!/usr/bin/env python3
"""Export interactive HTML studio for manual swing labeling."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared.types.models import Timeframe

from swing_engine import SwingEngine, SwingVisualizer
from scripts.run_benchmark_suite import load_bars
from swing_engine.datasets import load_manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Export labeling studio HTML")
    parser.add_argument("--dataset", default="XAUUSD_H1_human")
    parser.add_argument("--version", default="2.0.0")
    parser.add_argument("--output", type=Path, default=Path("debug/labeling_studio.html"))
    args = parser.parse_args()

    spec = next((s for s in load_manifest() if s.id == args.dataset), None)
    if not spec:
        print(f"Unknown dataset: {args.dataset}", file=sys.stderr)
        return 1

    bars = load_bars(spec)
    tf = Timeframe(spec.timeframe)
    result = SwingEngine(version=args.version).detect(bars, symbol=spec.symbol, timeframe=tf)
    viz = SwingVisualizer()
    viz.render_debug_html(result, bars, args.output)

    # Embed labeling instructions
    html = args.output.read_text(encoding="utf-8")
    note = (
        "<p style='color:#94a3b8;font-size:11px;padding:8px'>"
        "Labeling studio — click swings to inspect score breakdown. "
        "Export labels with scripts/generate_human_labels.py (independent truth) "
        "or edit benchmarks/labels/*.human.json manually.</p>"
    )
    html = html.replace("<div id=\"header\">", note + "<div id=\"header\">")
    args.output.write_text(html, encoding="utf-8")

    print(f"Labeling studio → {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

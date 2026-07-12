#!/usr/bin/env python3
"""Swing replay mode — step through bars and watch the engine think."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared.types.models import Timeframe

from swing_engine import SwingReplayEngine, SwingVisualizer, SwingEngine
from tests.swing_detection.fixtures import gold_candles, trend_candles


def _bars(symbol: str, n: int, tf: Timeframe):
    if symbol.upper().replace("/", "") == "XAUUSD":
        return gold_candles(n)
    return trend_candles(n, timeframe=tf)


def main() -> int:
    parser = argparse.ArgumentParser(description="Swing engine bar-by-bar replay")
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--timeframe", default="H1")
    parser.add_argument("--version", default="1.3.0")
    parser.add_argument("--bars", type=int, default=200)
    parser.add_argument("--min-bars", type=int, default=40)
    parser.add_argument("--step", type=int, default=5)
    parser.add_argument("--output", type=Path, default=Path("debug/swing_replay.json"))
    parser.add_argument("--studio", type=Path, help="Also render studio HTML with replay slider")
    args = parser.parse_args()

    tf = Timeframe(args.timeframe)
    bars = _bars(args.symbol, args.bars, tf)
    replay = SwingReplayEngine(version=args.version)
    session = replay.build_session(bars, symbol=args.symbol, timeframe=tf, min_bars=args.min_bars, step=args.step)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(session.to_dict(), indent=2), encoding="utf-8")
    print(f"Replay: {session.total_frames} frames → {args.output}")

    if args.studio:
        result = SwingEngine(version=args.version).detect(bars, symbol=args.symbol, timeframe=tf)
        frames = [f.to_dict() for f in session.frames]
        SwingVisualizer().render_debug_html(result, bars, args.studio, replay_frames=frames)
        print(f"Studio: {args.studio}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

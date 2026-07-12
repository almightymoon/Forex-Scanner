#!/usr/bin/env python3
"""Paper-mode swing validation runner (Sprint 3, Priority 5).

Runs the swing engine over a series of bars in "paper mode", logging every
confirmed swing with detection timestamps, and (optionally) scoring the log
against a human/benchmark review file to report *live* precision/recall/delay.

Usage:
    # Record swings on synthetic gold data into the paper log
    python scripts/paper_validate_swings.py --symbol XAUUSD --record

    # Score the paper log against a review file
    python scripts/paper_validate_swings.py --symbol XAUUSD \\
        --review benchmarks/labels/XAUUSD_H1.manual.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared.types.models import Timeframe

from swing_engine import (
    PaperSwingLog,
    SwingEngine,
    compare_against_review,
    get_config,
)
from swing_engine.utils import pip_size_for_symbol
from tests.swing_detection.fixtures import gold_candles, trend_candles


def _bars(symbol: str, n: int, tf: Timeframe):
    if symbol.upper().replace("/", "") == "XAUUSD":
        return gold_candles(n)
    return trend_candles(n, timeframe=tf)


def _load_review(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("swings", [])


def main() -> int:
    parser = argparse.ArgumentParser(description="Paper-mode swing validation")
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--timeframe", default="H1")
    parser.add_argument("--version", default="1.2.0")
    parser.add_argument("--bars", type=int, default=200)
    parser.add_argument("--log", type=Path, default=Path("benchmarks/live/paper_swings.jsonl"))
    parser.add_argument("--record", action="store_true", help="Detect and append swings to the paper log")
    parser.add_argument("--review", type=Path, help="Review JSON to score the paper log against")
    parser.add_argument("--tolerance-pips", type=float, default=5.0)
    parser.add_argument("--output", type=Path, help="Write live validation report JSON here")
    args = parser.parse_args()

    tf = Timeframe(args.timeframe)
    cfg = get_config(tf, version=args.version, symbol=args.symbol)
    log = PaperSwingLog(args.log)

    if args.record:
        bars = _bars(args.symbol, args.bars, tf)
        result = SwingEngine(cfg, version=args.version).detect(bars, symbol=args.symbol, timeframe=tf)
        new = log.record(result)
        ctx = result.artifacts.market_context
        print(f"Recorded {len(new)} new swing(s) to {args.log}")
        if ctx:
            print(f"Market context: {ctx.to_dict()}")

    if args.review:
        if not args.review.exists():
            print(f"Review file not found: {args.review}", file=sys.stderr)
            return 1
        reviewed = _load_review(args.review)
        logged = [e for e in log.load() if e["symbol"].upper() == args.symbol.upper()]
        price_tol = args.tolerance_pips * pip_size_for_symbol(args.symbol, cfg)
        res = compare_against_review(logged, reviewed, price_tolerance=price_tol)
        print("\n=== Live (paper) validation ===")
        print(f"Logged={res.total_logged} Reviewed={res.total_reviewed}")
        print(f"P={res.precision:.3f} R={res.recall:.3f} F1={res.f1_score:.3f} "
              f"delay={res.average_detection_delay_bars:.2f} bars")
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            payload = {"generated_at": datetime.utcnow().isoformat(), **res.to_dict()}
            args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            print(f"Report: {args.output}")

    if not args.record and not args.review:
        parser.error("Specify --record and/or --review")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

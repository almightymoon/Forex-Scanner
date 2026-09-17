#!/usr/bin/env python3
"""Settle open paper orders against live OHLC (no new entries).

Useful when the scanner daemon is off or rate-limited — does not open
trades and does not require a venue (OANDA/MT5).

Usage:
  PYTHONPATH=. python scripts/paper_broker_settle.py
  PYTHONPATH=. python scripts/paper_broker_settle.py --timeframe H1
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = val


async def _settle(timeframe_name: str) -> dict:
    from shared.types.models import Timeframe
    from services.broker_service import get_paper_broker, paper_broker_enabled, reset_paper_broker_singleton
    from services.scanner_service.pipeline import ScannerPipeline

    if not paper_broker_enabled():
        raise SystemExit("PAPER_BROKER_ENABLED is not true")

    reset_paper_broker_singleton()
    broker = get_paper_broker()
    before = broker.summary()
    symbols = sorted({o.symbol for o in broker._open.values()})
    if not symbols:
        return {"before": before, "closed": [], "symbols": [], "after": before}

    tf = Timeframe(timeframe_name)
    pipeline = ScannerPipeline()
    closed_ids: list[str] = []
    errors: list[dict] = []

    for symbol in symbols:
        try:
            candles = await pipeline.market_data.get_candles(symbol, tf, 120)
            if not candles:
                errors.append({"symbol": symbol, "error": "no_candles"})
                continue
            closed = broker.evaluate_open(symbol, candles)
            closed_ids.extend(o.id for o in closed)
        except Exception as exc:
            errors.append({"symbol": symbol, "error": str(exc)})

    after = broker.summary()
    return {
        "before": before,
        "symbols": symbols,
        "closed_ids": closed_ids,
        "errors": errors,
        "after": after,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeframe", default="H1")
    args = parser.parse_args()
    _load_dotenv(ROOT / ".env")
    payload = asyncio.run(_settle(args.timeframe))
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

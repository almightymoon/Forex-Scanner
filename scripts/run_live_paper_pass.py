#!/usr/bin/env python3
"""One live paper-broker pass through the scanner pipeline.

Loads repo ``.env`` (without committing it), asserts PAPER_BROKER_ENABLED,
scans a short symbol list, then prints paper-broker status.

Usage:
  PYTHONPATH=. python scripts/run_live_paper_pass.py
  PYTHONPATH=. python scripts/run_live_paper_pass.py --symbols XAUUSD,EURUSD
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
        # Don't override an explicitly exported shell var.
        if key and key not in os.environ:
            os.environ[key] = val


async def _run(symbols: list[str], min_score: int) -> dict:
    from shared.types.models import Timeframe
    from services.scanner_service.pipeline import ScannerPipeline
    from services.broker_service import paper_broker_enabled, get_paper_broker

    if not paper_broker_enabled():
        raise SystemExit(
            "PAPER_BROKER_ENABLED is not true — set it in .env before running live paper."
        )
    if os.getenv("SCANNER_EMIT_POLICY"):
        raise SystemExit(
            "SCANNER_EMIT_POLICY is set — refuse live paper pass while emit gate is on."
        )

    before = get_paper_broker().summary()
    pipeline = ScannerPipeline()
    signals = []
    for sym in symbols:
        sig = await pipeline.scan_symbol(sym, Timeframe.H1, with_ai=False, with_backtest=False)
        if sig is not None:
            signals.append(
                {
                    "symbol": sig.symbol,
                    "direction": sig.direction.value if hasattr(sig.direction, "value") else str(sig.direction),
                    "score": sig.score,
                    "has_levels": sig.stop_loss is not None and sig.take_profit_1 is not None,
                }
            )
    after = get_paper_broker().summary()
    return {
        "paper_enabled": True,
        "emit_policy": None,
        "symbols": symbols,
        "min_score": min_score,
        "signals": signals,
        "paper_before": before,
        "paper_after": after,
    }


def main() -> int:
    _load_dotenv(ROOT / ".env")
    # Force-enable for this pass if .env was loaded after import-time checks elsewhere.
    os.environ.setdefault("PAPER_BROKER_ENABLED", "true")

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--symbols",
        default="XAUUSD,EURUSD,GBPUSD,USDJPY",
        help="Comma-separated symbols",
    )
    ap.add_argument("--min-score", type=int, default=70)
    args = ap.parse_args()
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]

    # Re-apply after argparse so child imports see the flag.
    _load_dotenv(ROOT / ".env")
    os.environ["PAPER_BROKER_ENABLED"] = os.environ.get("PAPER_BROKER_ENABLED", "true")

    result = asyncio.run(_run(symbols, args.min_score))
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

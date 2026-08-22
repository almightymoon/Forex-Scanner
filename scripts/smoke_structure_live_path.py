#!/usr/bin/env python3
"""Live-path smoke: confirmed swings → structure → decision on XAUUSD.

Uses synthetic gold candles by default (no broker required). Pass --csv PATH
to exercise against exported H1 OHLC (symbol,timestamp,open,high,low,close,...
or standard MT5 export columns).
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.types.models import Candle, IndicatorValues, Timeframe
from services.quant_engine.decision.engine import DecisionEngine
from services.quant_engine.market_structure import analyze_structure
from services.quant_engine.swings.boundary import SCAN_SWING_VERSION, obtain_confirmed_swings
from swing_engine.versions import DEFAULT_VERSION
from tests.swing_detection.fixtures import gold_candles


def _parse_ts(value: str) -> datetime:
    for fmt in ("%Y.%m.%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value.strip(), fmt)
        except ValueError:
            continue
    return datetime.fromisoformat(value.replace("Z", "+00:00").replace(" ", "T"))


def load_csv(path: Path, symbol: str = "XAUUSD") -> list[Candle]:
    rows: list[Candle] = []
    with path.open(newline="") as fh:
        reader = csv.DictReader(fh)
        for i, row in enumerate(reader):
            ts_raw = row.get("timestamp") or row.get("time") or row.get("Date")
            if ts_raw is None and "Date" in row and "Time" in row:
                ts_raw = f"{row['Date']} {row['Time']}"
            if ts_raw is None:
                raise SystemExit(f"No timestamp column in {path}")
            open_ = float(row.get("open") or row.get("Open"))
            high = float(row.get("high") or row.get("High"))
            low = float(row.get("low") or row.get("Low"))
            close = float(row.get("close") or row.get("Close"))
            volume = float(row.get("volume") or row.get("Volume") or row.get("tick_volume") or 0)
            rows.append(
                Candle(
                    symbol=symbol,
                    timeframe=Timeframe.H1,
                    timestamp=_parse_ts(str(ts_raw)),
                    open=open_,
                    high=high,
                    low=low,
                    close=close,
                    volume=volume,
                )
            )
    if len(rows) < 50:
        raise SystemExit(f"Need >= 50 candles, got {len(rows)}")
    return rows


def _indicators(candles: list[Candle]) -> IndicatorValues:
    last = candles[-1]
    atr = max(0.5, sum(c.high - c.low for c in candles[-14:]) / 14)
    return IndicatorValues(
        symbol=last.symbol,
        timeframe=last.timeframe,
        timestamp=last.timestamp,
        ema_20=last.close,
        ema_50=candles[-50].close if len(candles) >= 50 else last.close,
        ema_200=candles[-200].close if len(candles) >= 200 else last.close,
        adx_14=22.0,
        rsi_14=52.0,
        macd_histogram=0.1,
        atr_14=atr,
        bb_lower=last.close - atr,
        bb_middle=last.close,
        bb_upper=last.close + atr,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=None, help="Optional OHLC CSV path")
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--bars", type=int, default=240, help="Synthetic bar count")
    args = parser.parse_args()

    candles = load_csv(args.csv, args.symbol) if args.csv else gold_candles(args.bars)
    swings = obtain_confirmed_swings(candles, version=SCAN_SWING_VERSION)
    snapshot = analyze_structure(candles, swings)
    signal = DecisionEngine().evaluate(
        args.symbol,
        Timeframe.H1,
        candles,
        _indicators(candles),
        [],
        confirmed_swings=swings,
        structure_snapshot=snapshot,
    )

    payload = {
        "default_version": DEFAULT_VERSION,
        "scan_swing_version": SCAN_SWING_VERSION,
        "bars": len(candles),
        "confirmed_swings": len(swings),
        "structure_events": len(snapshot.events),
        "structure_regime": (signal.market_features or {}).get("structure_regime"),
        "setup_confluence": (signal.market_features or {}).get("setup_confluence"),
        "direction": signal.direction.value,
        "score": signal.score,
        "confidence": signal.confidence,
        "warnings": signal.warnings[:8],
    }
    print(json.dumps(payload, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

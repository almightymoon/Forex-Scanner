#!/usr/bin/env python3
"""Live-path / paper-scan smoke: swings → structure → SMC → decision on XAUUSD.

Uses synthetic gold candles by default. Pass --csv PATH for real OHLC
(MT5 ExportXAUUSDH1Benchmark format). Use --tail to limit bars (full
history can be very slow under swing v2.3).
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.types.models import Candle, IndicatorValues, Timeframe
from services.quant_engine.decision.engine import DecisionEngine
from services.quant_engine.detection.smc import SMCEngine
from services.quant_engine.liquidity import liquidity_overlay_payload
from services.quant_engine.liquidity.pools import build_liquidity_map
from services.quant_engine.market_structure import analyze_structure
from services.quant_engine.market_structure.mtf_bias import compute_mtf_structure_bias_from_h1
from services.quant_engine.market_structure.studio import structure_overlay_payload
from services.quant_engine.swings.boundary import SCAN_SWING_VERSION, obtain_confirmed_swings
from swing_engine import SwingEngine, SwingVisualizer, get_config
from swing_engine.versions import DEFAULT_VERSION
from tests.swing_detection.fixtures import gold_candles


def _parse_ts(value: str) -> datetime:
    for fmt in ("%Y.%m.%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value.strip(), fmt)
        except ValueError:
            continue
    return datetime.fromisoformat(value.replace("Z", "+00:00").replace(" ", "T"))


def _open_text(path: Path):
    if path.suffix == ".gz" or path.name.endswith(".csv.gz"):
        return gzip.open(path, "rt", newline="")
    return path.open(newline="")


def load_csv(path: Path, symbol: str = "XAUUSD") -> list[Candle]:
    rows: list[Candle] = []
    with _open_text(path) as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            ts_raw = (
                row.get("timestamp")
                or row.get("timestamp_server")
                or row.get("time")
                or row.get("Date")
            )
            if ts_raw is None and "Date" in row and "Time" in row:
                ts_raw = f"{row['Date']} {row['Time']}"
            if ts_raw is None:
                raise SystemExit(f"No timestamp column in {path}")
            open_ = float(row.get("open") or row.get("Open"))
            high = float(row.get("high") or row.get("High"))
            low = float(row.get("low") or row.get("Low"))
            close = float(row.get("close") or row.get("Close"))
            volume = float(
                row.get("volume") or row.get("Volume") or row.get("tick_volume") or 0
            )
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
    parser.add_argument(
        "--tail",
        type=int,
        default=2000,
        help="When --csv is set, use only the last N bars (0 = all)",
    )
    parser.add_argument(
        "--html",
        type=Path,
        default=None,
        help="Optional path to write swing+structure+liquidity debug HTML",
    )
    args = parser.parse_args()

    if args.csv:
        candles = load_csv(args.csv, args.symbol)
        if args.tail and args.tail > 0:
            candles = candles[-args.tail :]
    else:
        candles = gold_candles(args.bars)

    swings = obtain_confirmed_swings(candles, version=SCAN_SWING_VERSION)
    snapshot = analyze_structure(candles, swings)
    smc_patterns = SMCEngine().detect_all(
        candles,
        args.symbol,
        Timeframe.H1,
        confirmed_swings=swings,
        structure_snapshot=snapshot,
    )
    mtf = compute_mtf_structure_bias_from_h1(
        candles, include_h1=True, min_bars=30
    )
    signal = DecisionEngine().evaluate(
        args.symbol,
        Timeframe.H1,
        candles,
        _indicators(candles),
        smc_patterns,
        mtf_trends=mtf.trends,
        confirmed_swings=swings,
        structure_snapshot=snapshot,
    )

    features = signal.market_features or {}
    liq_dict = features.get("liquidity_map") or {}
    liquidity_map = build_liquidity_map(
        smc_patterns,
        candles=candles,
        snapshot=snapshot,
    )
    liq_overlay = liquidity_overlay_payload(liquidity_map)

    html_path = None
    if args.html:
        overlay = structure_overlay_payload(snapshot)
        cfg = get_config(Timeframe.H1, version=SCAN_SWING_VERSION, symbol=args.symbol)
        result = SwingEngine(cfg, version=SCAN_SWING_VERSION).detect(
            candles, symbol=args.symbol, timeframe=Timeframe.H1
        )
        html_path = str(
            SwingVisualizer().render_debug_html(
                result,
                candles,
                args.html,
                structure_events=overlay["structure_events"],
                structure_context=overlay["structure_context"],
                liquidity_overlay=liq_overlay,
            )
        )

    engine_by_name = {
        o.get("name"): o for o in (signal.engine_outputs or []) if isinstance(o, dict)
    }
    payload = {
        "default_version": DEFAULT_VERSION,
        "scan_swing_version": SCAN_SWING_VERSION,
        "bars": len(candles),
        "confirmed_swings": len(swings),
        "smc_patterns": len(smc_patterns),
        "structure_events": len(snapshot.events),
        "structure_regime": features.get("structure_regime"),
        "external_bias": snapshot.external_bias.value,
        "mtf_structure_trends": mtf.to_dict()["trends"],
        "mtf_structure_biases": {
            k: v.to_dict() for k, v in mtf.biases.items()
        },
        "setup_confluence": features.get("setup_confluence"),
        "session_trend": features.get("session_trend")
        or (engine_by_name.get("Trend") or {}).get("metadata", {}).get("session_trend"),
        "liquidity": {
            "levels": len(liquidity_map.levels),
            "sweeps": len(liquidity_map.sweeps),
            "session_tags": list(liquidity_map.session_tags),
            "from_features": bool(liq_dict),
        },
        "order_block": {
            "score": (engine_by_name.get("Order Block") or {}).get("score"),
            "proximity_boosts": sum(
                1
                for q in ((engine_by_name.get("Order Block") or {}).get("metadata") or {}).get(
                    "qualities", []
                )
                if q.get("structure_proximity", {}).get("boost")
            ),
        },
        "fair_value_gap": {
            "score": (engine_by_name.get("Fair Value Gap") or {}).get("score"),
            "proximity_boosts": sum(
                1
                for g in ((engine_by_name.get("Fair Value Gap") or {}).get("metadata") or {}).get(
                    "gaps", []
                )
                if g.get("structure_proximity", {}).get("boost")
            ),
        },
        "direction": signal.direction.value,
        "score": signal.score,
        "confidence": signal.confidence,
        "warnings": signal.warnings[:8],
        "html": html_path,
    }
    print(json.dumps(payload, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Offline paper-broker twin for frozen 1.4.0 (baseline stream only).

Uses the same cadence/execution as OOS validation. Does NOT set
SCANNER_EMIT_POLICY and does not apply H4 gates.

Usage:
  python scripts/paper_broker_1_4_0.py \\
    --csv benchmarks/data/retrospective/XAUUSD/H1_2022_2024_v1/XAUUSD_H1_2022_2024.real.csv.gz \\
    --start 2024-07-01 --end 2024-07-11

  python scripts/paper_broker_1_4_0.py --csv chart_csv/FXNavigators_XAUUSD_H1.csv --tail 800
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Ensure offline run never inherits a live emit gate.
os.environ.pop("SCANNER_EMIT_POLICY", None)

from shared.types.models import NewsContext, SignalDirection, Timeframe
from services.backtesting_service.execution import (
    ExecutionConfig,
    SimulatedTrade,
    compute_performance_metrics,
    pip_size_for_symbol,
    simulate_trade,
)
from services.broker_service.paper import PaperBroker
from services.quant_engine.decision.engine import DecisionEngine
from services.quant_engine.pipeline import ANALYSIS_PIPELINE_VERSION, analyze_candle_window
from swing_engine.benchmark_data import load_candles_csv
from scripts.smoke_structure_live_path import load_csv as load_csv_flexible

OUT_DIR = ROOT / "benchmarks" / "live" / "paper_broker"
LOOKBACK = 250
STRIDE = 4
MIN_SCORE = 70
FORWARD_BARS = 20
COOLDOWN = FORWARD_BARS // 2
BASE_EXEC = ExecutionConfig("signal_close", "sl_first", 0.0, 0.0, 0.0)


def _parse_day(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def load_candles(path: Path, symbol: str):
    try:
        return load_candles_csv(path, symbol=symbol, timeframe=Timeframe.H1)
    except Exception:
        return load_csv_flexible(path, symbol=symbol)


def run_paper(
    candles,
    *,
    start: datetime | None,
    end: datetime | None,
    min_score: int,
    out_dir: Path,
) -> dict[str, Any]:
    engine = DecisionEngine()
    news = NewsContext(score=10)
    broker = PaperBroker(out_dir=out_dir, config=BASE_EXEC, forward_bars=FORWARD_BARS, min_score=min_score)

    # Fresh offline book for this run.
    for p in (broker.open_path, broker.closed_path, broker.intents_path):
        if p.exists():
            p.unlink()
    broker._open.clear()

    sims: list[SimulatedTrade] = []
    n_signals = 0
    cooldown_until = -1
    pip = pip_size_for_symbol(candles[0].symbol if candles else "XAUUSD")

    for i in range(LOOKBACK, len(candles) - FORWARD_BARS, STRIDE):
        bar = candles[i]
        ts = bar.timestamp
        if start and ts < start:
            continue
        if end and ts > end:
            break
        if i < cooldown_until:
            continue

        window = candles[i - LOOKBACK + 1 : i + 1]
        bundle = analyze_candle_window(
            bar.symbol,
            Timeframe.H1,
            window,
            news=news,
            decision_engine=engine,
            evaluate=True,
        )
        signal = bundle.signal
        if signal is None or signal.score < min_score:
            continue
        if signal.direction not in (SignalDirection.BUY, SignalDirection.SELL):
            continue
        if signal.stop_loss is None or signal.take_profit_1 is None:
            continue

        n_signals += 1
        entry = float(window[-1].close)
        order = broker.open_from_signal(
            signal,
            entry_price=entry,
            signal_bar_ts=ts.isoformat(),
        )
        forward = candles[i + 1 : i + 1 + FORWARD_BARS]
        if order is not None:
            closed = broker.settle_with_forward(order, forward)
            if closed is not None:
                sims.append(
                    SimulatedTrade(
                        entry_price=closed.entry_price,
                        exit_price=float(closed.exit_price or closed.entry_price),
                        direction=closed.direction,
                        outcome=closed.outcome or "breakeven",
                        pnl_pips=float(closed.pnl_pips or 0),
                        pnl_price=0.0,
                        risk_price=1.0,
                        r_multiple=float(closed.r_multiple or 0),
                        score=closed.score,
                        ambiguous=closed.ambiguous,
                        bars_held=int(closed.bars_held or 0),
                    )
                )
                cooldown_until = i + COOLDOWN
                continue

        # Fallback direct simulate (should match settle) if journal skipped.
        sim = simulate_trade(
            direction=signal.direction.value,
            entry=entry,
            stop_loss=float(signal.stop_loss),
            take_profit=float(signal.take_profit_1),
            forward_bars=forward,
            pip=pip,
            score=signal.score,
            config=BASE_EXEC,
        )
        sims.append(sim)
        cooldown_until = i + COOLDOWN

    metrics = compute_performance_metrics(sims).to_dict() if sims else {
        "total_trades": 0,
        "expectancy": 0.0,
        "profit_factor": None,
        "win_rate": 0.0,
    }
    metrics["total_r"] = round(sum(t.r_multiple for t in sims), 4)
    summary = {
        "pipeline_version": ANALYSIS_PIPELINE_VERSION,
        "emit_policy": None,
        "signals": n_signals,
        "fills": len(sims),
        "metrics": metrics,
        "out_dir": str(out_dir),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", type=Path, required=True)
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--start", default=None)
    ap.add_argument("--end", default=None)
    ap.add_argument("--tail", type=int, default=0)
    ap.add_argument("--min-score", type=int, default=MIN_SCORE)
    ap.add_argument("--out", type=Path, default=OUT_DIR)
    args = ap.parse_args()

    candles = load_candles(args.csv, args.symbol)
    if args.tail and args.tail > 0:
        candles = candles[-args.tail :]
    summary = run_paper(
        candles,
        start=_parse_day(args.start),
        end=_parse_day(args.end),
        min_score=args.min_score,
        out_dir=args.out,
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

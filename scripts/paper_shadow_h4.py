#!/usr/bin/env python3
"""Paper-shadow monitor for provisional H4 emit gate.

Compares frozen 1.4.0 baseline emissions vs ``h4_rank1_liquidity_none``
without changing live defaults (does not set SCANNER_EMIT_POLICY globally).

Usage:
  python scripts/paper_shadow_h4.py \\
    --csv benchmarks/data/retrospective/XAUUSD/H1_2022_2024_v1/XAUUSD_H1_2022_2024.real.csv.gz \\
    --start 2024-07-01 --end 2024-07-11

  python scripts/paper_shadow_h4.py --csv chart_csv/FXNavigators_XAUUSD_H1.csv --tail 800

Artifacts land in benchmarks/live/h4_paper_shadow/ (append-safe JSONL + summary).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.types.models import NewsContext, SignalDirection, Timeframe
from services.backtesting_service.execution import (
    ExecutionConfig,
    SimulatedTrade,
    compute_performance_metrics,
    pip_size_for_symbol,
    simulate_trade,
)
from services.quant_engine.decision.engine import DecisionEngine
from services.quant_engine.pipeline import ANALYSIS_PIPELINE_VERSION, analyze_candle_window
from services.quant_engine.pipeline.analyze import _primary_zone_labels
from services.quant_engine.pipeline.calibration_1_8_0 import (
    CANDIDATE_POLICIES,
    EmitPolicy,
)
from services.quant_engine.pipeline.emit_policy import apply_emit_policy
from services.smc_service.smc import SMCEngine
from swing_engine.benchmark_data import load_candles_csv

# Reuse CSV loader from smoke when path is not the benchmark helper format
from scripts.smoke_structure_live_path import load_csv as load_csv_flexible

DEFAULT_POLICY = "h4_rank1_liquidity_none"
OUT_DIR = ROOT / "benchmarks" / "live" / "h4_paper_shadow"
LOOKBACK = 250
STRIDE = 4
MIN_SCORE = 70
FORWARD_BARS = 20
BASE_EXEC = ExecutionConfig("signal_close", "sl_first", 0.0, 0.0, 0.0)


def _parse_day(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def _policy(name: str) -> EmitPolicy:
    for p in CANDIDATE_POLICIES:
        if p.name == name:
            return p
    raise SystemExit(f"unknown policy {name}")


def _metrics(sims: list[SimulatedTrade]) -> dict[str, Any]:
    if not sims:
        return {"total_trades": 0, "expectancy": 0.0, "profit_factor": 0.0, "win_rate": 0.0, "total_r": 0.0}
    m = compute_performance_metrics(sims).to_dict()
    m["total_r"] = round(sum(t.r_multiple for t in sims), 4)
    return m


def load_candles(path: Path, symbol: str) -> list:
    try:
        return load_candles_csv(path, symbol=symbol, timeframe=Timeframe.H1)
    except Exception:
        return load_csv_flexible(path, symbol=symbol)


def run_shadow(
    candles,
    *,
    policy: EmitPolicy,
    start: datetime | None,
    end: datetime | None,
    min_score: int,
) -> dict[str, Any]:
    engine = DecisionEngine()
    smc = SMCEngine()
    news = NewsContext(score=10)
    pip = pip_size_for_symbol("XAUUSD")

    baseline_events: list[dict] = []
    gated_events: list[dict] = []
    baseline_sims: list[SimulatedTrade] = []
    gated_sims: list[SimulatedTrade] = []
    suppressed = 0
    cooldown_b = 0
    cooldown_g = 0

    start_i = 0
    end_i = len(candles) - 1
    if start is not None:
        start_i = next((i for i, c in enumerate(candles) if c.timestamp >= start), 0)
    if end is not None:
        end_i = next((i for i in range(len(candles) - 1, -1, -1) if candles[i].timestamp <= end), end_i)

    t0 = time.perf_counter()
    for i in range(max(start_i, LOOKBACK - 1), end_i - FORWARD_BARS + 1):
        if (i - start_i) % STRIDE != 0:
            continue
        window = candles[max(0, i - LOOKBACK + 1) : i + 1]
        if (i - start_i) % 200 == 0:
            print(f"  {candles[i].timestamp.isoformat()} …", flush=True)

        # Ensure env gate is off so analyze returns raw 1.4.0 signal
        bundle = analyze_candle_window(
            "XAUUSD",
            Timeframe.H1,
            window,
            news=news,
            decision_engine=engine,
            smc_engine=smc,
            evaluate=True,
        )
        signal = bundle.signal
        if (
            signal is None
            or signal.score < min_score
            or signal.direction == SignalDirection.NEUTRAL
            or not signal.stop_loss
            or not signal.take_profit_1
        ):
            continue

        labels = _primary_zone_labels(list(bundle.smc_patterns), signal.direction.value)
        ts = window[-1].timestamp.isoformat()
        entry = window[-1].close
        base_row = {
            "timestamp": ts,
            "direction": signal.direction.value,
            "score": signal.score,
            "confidence": signal.confidence,
            "entry": entry,
            "stop_loss": signal.stop_loss,
            "take_profit_1": signal.take_profit_1,
            "primary_rank": labels.get("primary_rank"),
            "liquidity_relation": labels.get("liquidity_relation"),
            "pipeline_version": ANALYSIS_PIPELINE_VERSION,
            "stream": "baseline_1_4_0",
        }

        # Baseline stream (ungated)
        if cooldown_b <= 0:
            baseline_events.append(base_row)
            sim = simulate_trade(
                direction=signal.direction.value,
                entry=entry,
                stop_loss=signal.stop_loss,
                take_profit=signal.take_profit_1,
                forward_bars=candles[i + 1 : i + 1 + FORWARD_BARS],
                pip=pip,
                score=signal.score,
                config=BASE_EXEC,
            )
            baseline_sims.append(sim)
            cooldown_b = FORWARD_BARS // 2
        else:
            cooldown_b -= 1

        # Gated stream — clone so apply_emit_policy cannot mutate baseline fields
        gated_signal = apply_emit_policy(_clone_signal(signal), policy=policy, labels=labels)
        passed = gated_signal.direction != SignalDirection.NEUTRAL and gated_signal.score >= min_score
        if not passed:
            suppressed += 1
            continue
        if cooldown_g <= 0:
            gated_events.append({**base_row, "stream": policy.name, "emit_policy_passed": True})
            sim_g = simulate_trade(
                direction=gated_signal.direction.value,
                entry=entry,
                stop_loss=gated_signal.stop_loss or signal.stop_loss,
                take_profit=gated_signal.take_profit_1 or signal.take_profit_1,
                forward_bars=candles[i + 1 : i + 1 + FORWARD_BARS],
                pip=pip,
                score=gated_signal.score,
                config=BASE_EXEC,
            )
            gated_sims.append(sim_g)
            cooldown_g = FORWARD_BARS // 2
        else:
            cooldown_g -= 1

    elapsed = time.perf_counter() - t0
    return {
        "runtime_seconds": round(elapsed, 2),
        "policy": policy.to_dict(),
        "baseline_events": baseline_events,
        "gated_events": gated_events,
        "suppressed_count": suppressed,
        "baseline_metrics": _metrics(baseline_sims),
        "gated_metrics": _metrics(gated_sims),
        "baseline_trades": len(baseline_sims),
        "gated_trades": len(gated_sims),
    }


def _clone_signal(signal):
    """Shallow dataclass copy so apply_emit_policy can mutate safely."""
    from dataclasses import replace

    return replace(signal, market_features=dict(signal.market_features or {}), warnings=list(signal.warnings or []))


def write_artifacts(result: dict, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    events_path = out_dir / "events.jsonl"
    with events_path.open("a", encoding="utf-8") as fh:
        for row in result["baseline_events"]:
            fh.write(json.dumps({**row, "run_id": run_id}) + "\n")
        for row in result["gated_events"]:
            fh.write(json.dumps({**row, "run_id": run_id}) + "\n")

    summary = {
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pipeline_baseline": ANALYSIS_PIPELINE_VERSION,
        "policy": result["policy"],
        "runtime_seconds": result["runtime_seconds"],
        "suppressed_count": result["suppressed_count"],
        "baseline_trades": result["baseline_trades"],
        "gated_trades": result["gated_trades"],
        "baseline_metrics": result["baseline_metrics"],
        "gated_metrics": result["gated_metrics"],
        "note": (
            "Paper shadow only. Live default remains ungated 1.4.0. "
            "Enable live opt-in with SCANNER_EMIT_POLICY=h4_rank1_liquidity_none after review."
        ),
    }
    (out_dir / f"summary_{run_id}.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (out_dir / "latest_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)
    print(f"wrote {events_path} and summary_{run_id}.json", flush=True)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--csv", type=Path, required=True)
    p.add_argument("--symbol", default="XAUUSD")
    p.add_argument("--policy", default=DEFAULT_POLICY)
    p.add_argument("--start", type=str, default=None, help="UTC date YYYY-MM-DD")
    p.add_argument("--end", type=str, default=None, help="UTC date YYYY-MM-DD")
    p.add_argument("--tail", type=int, default=0, help="Use only last N candles")
    p.add_argument("--min-score", type=int, default=MIN_SCORE)
    p.add_argument("--out", type=Path, default=OUT_DIR)
    args = p.parse_args()

    # Never inherit a live emit policy from the shell for this comparison run.
    import os

    os.environ.pop("SCANNER_EMIT_POLICY", None)

    print(f"loading {args.csv} …", flush=True)
    candles = load_candles(args.csv, args.symbol)
    if args.tail and args.tail > 0:
        candles = candles[-args.tail :]
    print(f"candles={len(candles)} policy={args.policy}", flush=True)

    result = run_shadow(
        candles,
        policy=_policy(args.policy),
        start=_parse_day(args.start),
        end=_parse_day(args.end),
        min_score=args.min_score,
    )
    write_artifacts(result, args.out)


if __name__ == "__main__":
    main()

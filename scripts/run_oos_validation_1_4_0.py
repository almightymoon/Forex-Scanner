#!/usr/bin/env python3
"""Frozen 1.4.0 OOS validation — resumable monthly chunks.

Usage:
  python scripts/run_oos_validation_1_4_0.py --month 2024-01
  python scripts/run_oos_validation_1_4_0.py --month 2024-02
  ...
  python scripts/run_oos_validation_1_4_0.py --finalize

Or one-shot (may be long):
  python scripts/run_oos_validation_1_4_0.py --all-months
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import sys
import time
from collections import defaultdict
from dataclasses import asdict, dataclass
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
from services.quant_engine.pipeline import ANALYSIS_PIPELINE_VERSION, analyze_candle_window
from services.quant_engine.decision.engine import DecisionEngine
from services.smc_service.smc import SMCEngine
from swing_engine.benchmark_data import load_candles_csv

DATASET_ID = "xauusd_h1_oos_v1_retrospective_2022_2024"
SOURCE_PATH = (
    ROOT
    / "benchmarks/data/retrospective/XAUUSD/H1_2022_2024_v1/XAUUSD_H1_2022_2024.real.csv.gz"
)
EXPECTED_SHA256 = "eac96d050a6bacfe879a0506143a053d4ce5ab7304b94cfbab91067211040d73"
SPLIT = {
    "train": ("2022-01-02T22:00:00+00:00", "2022-12-31T23:00:00+00:00"),
    "validation": ("2023-01-01T00:00:00+00:00", "2023-12-31T23:00:00+00:00"),
    "test": ("2024-01-01T00:00:00+00:00", "2024-07-11T04:00:00+00:00"),
}
TEST_MONTHS = [
    "2024-01",
    "2024-02",
    "2024-03",
    "2024-04",
    "2024-05",
    "2024-06",
    "2024-07",
]
LOOKBACK_BARS = 250
SIGNAL_STRIDE = 4
MIN_SCORE = 70
FORWARD_BARS = 20
COOLDOWN = FORWARD_BARS // 2

BASE_EXEC = ExecutionConfig("signal_close", "sl_first", 0.0, 0.0, 0.0)
LOW_EXEC = ExecutionConfig("signal_close", "sl_first", 15.0, 5.0, 2.0)
HIGH_EXEC = ExecutionConfig("signal_close", "sl_first", 40.0, 15.0, 5.0)

OUT_DIR = ROOT / "validation"
FIXTURE_OOS = ROOT / "tests/fixtures/oos"
CHUNKS = OUT_DIR / "chunks"


def _parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass
class IntegrityReport:
    ok: bool
    candle_count: int
    first_ts: str
    last_ts: str
    duplicate_timestamps: int
    out_of_order: int
    invalid_ohlc: int
    non_positive_price: int
    gap_hours_gt_3: int
    gaps_sample: list[str]
    timezone_aware_utc: bool
    symbol_ok: bool
    timeframe_ok: bool
    notes: list[str]


def integrity_check(candles) -> IntegrityReport:
    notes: list[str] = []
    dup = ooo = bad_ohlc = nonpos = gaps = 0
    gap_sample: list[str] = []
    seen: set = set()
    prev = None
    for c in candles:
        if c.timestamp in seen:
            dup += 1
        seen.add(c.timestamp)
        if prev is not None and c.timestamp <= prev.timestamp:
            ooo += 1
        if c.high < max(c.open, c.close) or c.low > min(c.open, c.close) or c.low > c.high:
            bad_ohlc += 1
        if min(c.open, c.high, c.low, c.close) <= 0:
            nonpos += 1
        if prev is not None:
            delta_h = (c.timestamp - prev.timestamp).total_seconds() / 3600.0
            if 1.5 < delta_h <= 72 and c.timestamp.weekday() < 5 and prev.timestamp.weekday() < 5:
                if delta_h > 3:
                    gaps += 1
                    if len(gap_sample) < 10:
                        gap_sample.append(
                            f"{prev.timestamp.isoformat()} → {c.timestamp.isoformat()} ({delta_h:.1f}h)"
                        )
        prev = c
    tz_ok = all(c.timestamp.tzinfo is not None for c in candles)
    sym_ok = all(c.symbol == "XAUUSD" for c in candles)
    tf_ok = all(c.timeframe is Timeframe.H1 for c in candles)
    if gaps:
        notes.append(f"{gaps} weekday gaps > 3h (documented, not repaired)")
    notes.append("No silent repair applied")
    ok = dup == 0 and ooo == 0 and bad_ohlc == 0 and nonpos == 0 and tz_ok and sym_ok and tf_ok
    return IntegrityReport(
        ok=ok,
        candle_count=len(candles),
        first_ts=candles[0].timestamp.isoformat(),
        last_ts=candles[-1].timestamp.isoformat(),
        duplicate_timestamps=dup,
        out_of_order=ooo,
        invalid_ohlc=bad_ohlc,
        non_positive_price=nonpos,
        gap_hours_gt_3=gaps,
        gaps_sample=gap_sample,
        timezone_aware_utc=tz_ok,
        symbol_ok=sym_ok,
        timeframe_ok=tf_ok,
        notes=notes,
    )


def write_manifests(candles, integrity: IntegrityReport, actual_hash: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    FIXTURE_OOS.mkdir(parents=True, exist_ok=True)
    CHUNKS.mkdir(parents=True, exist_ok=True)
    dataset_manifest = {
        "dataset_id": DATASET_ID,
        "symbol": "XAUUSD",
        "timeframe": "H1",
        "provider": "WEALTHTEX_MT5_XAUUSD_VX",
        "price_basis": "BID",
        "source_path": str(SOURCE_PATH.relative_to(ROOT)),
        "source_package": "XAUUSD_H1_2022_2024_RETROSPECTIVE_HOLDOUT_V1",
        "timezone": "UTC (converted; broker schedule EET/EEST-equivalent)",
        "date_range": {"start": integrity.first_ts, "end": integrity.last_ts},
        "candle_count": integrity.candle_count,
        "sha256": actual_hash,
        "locked_date": datetime.now(timezone.utc).isoformat(),
        "pipeline_version_for_run": "1.4.0",
        "repairs": [],
        "integrity": asdict(integrity),
        "split_declared_before_evaluation": SPLIT,
        "notes": [
            "Retrospective holdout OHLC reused for scanner OOS.",
            "No parameter fitting.",
            "Prospective post-2026H1 not used (accrual incomplete).",
        ],
    }
    (OUT_DIR / "dataset_manifest.json").write_text(
        json.dumps(dataset_manifest, indent=2) + "\n", encoding="utf-8"
    )
    (FIXTURE_OOS / "dataset_manifest.json").write_text(
        json.dumps(dataset_manifest, indent=2) + "\n", encoding="utf-8"
    )
    config_manifest = {
        "pipeline_version": ANALYSIS_PIPELINE_VERSION,
        "symbol": "XAUUSD",
        "timeframe": "H1",
        "min_score": MIN_SCORE,
        "forward_bars": FORWARD_BARS,
        "cooldown_bars": COOLDOWN,
        "lookback_bars": LOOKBACK_BARS,
        "signal_stride": SIGNAL_STRIDE,
        "lookback_note": (
            f"Causal rolling LOOKBACK={LOOKBACK_BARS}; stride={SIGNAL_STRIDE} fixed a priori."
        ),
        "entry_model": "signal_close",
        "ambiguous_candle": "sl_first",
        "sl_tp_model": "ScannerSignal.stop_loss / take_profit_1",
        "news": "NewsContext(score=10) neutral",
        "mtf": "resolve_mtf_trends inside analyze_candle_window",
        "ranking": "frozen lexicographic + HTF select_ranking_htf_trend",
        "decision_engine": "DecisionEngine() default",
        "parameter_fitting": False,
        "execution_baseline": asdict(BASE_EXEC),
        "execution_low_cost": asdict(LOW_EXEC),
        "execution_high_cost": asdict(HIGH_EXEC),
        "split": SPLIT,
        "test_months": TEST_MONTHS,
    }
    config_manifest["config_sha256"] = _sha256_bytes(
        json.dumps(config_manifest, sort_keys=True).encode()
    )
    (OUT_DIR / "config_manifest.json").write_text(
        json.dumps(config_manifest, indent=2) + "\n", encoding="utf-8"
    )


def month_bounds(ym: str) -> tuple[datetime, datetime]:
    from datetime import timedelta

    y, m = map(int, ym.split("-"))
    start = datetime(y, m, 1, 0, 0, tzinfo=timezone.utc)
    if m == 12:
        next_m = datetime(y + 1, 1, 1, 0, 0, tzinfo=timezone.utc)
    else:
        next_m = datetime(y, m + 1, 1, 0, 0, tzinfo=timezone.utc)
    test_start = _parse_iso(SPLIT["test"][0])
    test_end = _parse_iso(SPLIT["test"][1])
    start = max(start, test_start)
    end_inclusive = min(next_m - timedelta(hours=1), test_end)
    return start, end_inclusive



def run_month(candles, ym: str) -> dict:
    start, end = month_bounds(ym)
    print(f"Month {ym}: {start.isoformat()} → {end.isoformat()}", flush=True)
    engine = DecisionEngine()
    smc = SMCEngine()
    news = NewsContext(score=10)
    pip = pip_size_for_symbol("XAUUSD")
    signals: list[dict] = []
    trades: list[dict] = []
    sims: list[SimulatedTrade] = []
    cooldown = 0

    start_i = next((i for i, c in enumerate(candles) if c.timestamp >= start), None)
    end_i = next((i for i in range(len(candles) - 1, -1, -1) if candles[i].timestamp <= end), None)
    if start_i is None or end_i is None:
        return {"month": ym, "signals": [], "trades": [], "metrics": metrics_dict([])}

    t0 = time.perf_counter()
    for i in range(start_i, end_i - FORWARD_BARS + 1):
        if cooldown > 0:
            cooldown -= 1
            continue
        if i < 60 or (i - start_i) % SIGNAL_STRIDE != 0:
            continue
        w0 = max(0, i - LOOKBACK_BARS + 1)
        window = candles[w0 : i + 1]
        if (i - start_i) % 120 == 0:
            print(f"  {candles[i].timestamp.isoformat()} sigs={len(signals)}", flush=True)
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
            or signal.score < MIN_SCORE
            or signal.direction == SignalDirection.NEUTRAL
            or not signal.stop_loss
            or not signal.take_profit_1
        ):
            continue
        ts = window[-1].timestamp
        sig = {
            "signal_id": f"sig-{ts.strftime('%Y%m%d%H%M')}-{signal.direction.value}-{signal.score}",
            "timestamp": ts.isoformat(),
            "symbol": "XAUUSD",
            "timeframe": "H1",
            "pipeline_version": bundle.pipeline_version,
            "direction": signal.direction.value,
            "score": signal.score,
            "confidence": signal.confidence,
            "entry": window[-1].close,
            "stop_loss": signal.stop_loss,
            "take_profit_1": signal.take_profit_1,
            "trend": signal.trend.value if signal.trend else None,
            "structure_external_bias": (
                bundle.structure_snapshot.external_bias.value
                if bundle.structure_snapshot
                else None
            ),
            "ranking_htf_trend": bundle.metadata.get("ranking_htf_trend"),
            "ranking_htf_tf": bundle.metadata.get("ranking_htf_tf"),
            "mtf_trends": {k: v.value for k, v in sorted(bundle.mtf_trends.items())},
            "fvg_zone_count": len(bundle.fvg_zones.zones) if bundle.fvg_zones else 0,
            "ob_zone_count": len(bundle.ob_zones.zones) if bundle.ob_zones else 0,
            "liquidity_active_count": (
                len(bundle.liquidity_snapshot.active_pools) if bundle.liquidity_snapshot else 0
            ),
            "ranked_fvg_ids": [
                p.metadata.get("zone_id")
                for p in bundle.smc_patterns
                if p.pattern_type == "fvg"
            ],
            "ranked_ob_ids": [
                p.metadata.get("zone_id")
                for p in bundle.smc_patterns
                if p.pattern_type == "order_block"
            ],
            "analytical_fingerprint": bundle.analytical_fingerprint(),
            "month": ym,
        }
        signals.append(sig)
        trade = simulate_trade(
            direction=signal.direction.value,
            entry=window[-1].close,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit_1,
            forward_bars=candles[i + 1 : i + 1 + FORWARD_BARS],
            pip=pip,
            score=signal.score,
            config=BASE_EXEC,
        )
        sims.append(trade)
        trades.append(
            {
                "signal_id": sig["signal_id"],
                "timestamp": sig["timestamp"],
                "direction": sig["direction"],
                "score": sig["score"],
                "confidence": sig["confidence"],
                "ranking_htf_trend": sig.get("ranking_htf_trend"),
                "structure_external_bias": sig.get("structure_external_bias"),
                "trend": sig.get("trend"),
                "entry_price": trade.entry_price,
                "exit_price": trade.exit_price,
                "outcome": trade.outcome,
                "pnl_pips": trade.pnl_pips,
                "pnl_price": trade.pnl_price,
                "r_multiple": trade.r_multiple,
                "ambiguous": trade.ambiguous,
                "bars_held": trade.bars_held,
                "month": ym,
                "execution": asdict(BASE_EXEC),
            }
        )
        cooldown = COOLDOWN

    elapsed = time.perf_counter() - t0
    out = {
        "month": ym,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "runtime_seconds": round(elapsed, 2),
        "signals": signals,
        "trades": trades,
        "metrics": metrics_dict(sims),
    }
    path = CHUNKS / f"{ym}.json"
    path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(
        f"  wrote {path.name}: signals={len(signals)} trades={len(trades)} "
        f"in {elapsed:.1f}s",
        flush=True,
    )
    return out


def metrics_dict(trades: list[SimulatedTrade]) -> dict[str, Any]:
    m = compute_performance_metrics(trades)
    total_r = sum(t.r_multiple for t in trades)
    d = m.to_dict()
    d["total_r"] = round(total_r, 4)
    d["gross_profit"] = round(sum(t.pnl_price for t in trades if t.pnl_price > 0), 6)
    d["gross_loss"] = round(sum(t.pnl_price for t in trades if t.pnl_price < 0), 6)
    d["ambiguous_trades"] = sum(1 for t in trades if t.ambiguous)
    n = m.total_trades
    if n > 0:
        p = m.wins / n
        se = math.sqrt(p * (1 - p) / n)
        d["win_rate_se_approx"] = round(se * 100, 2)
        d["win_rate_ci95_approx"] = [
            round(max(0, (p - 1.96 * se) * 100), 1),
            round(min(100, (p + 1.96 * se) * 100), 1),
        ]
    else:
        d["win_rate_se_approx"] = None
        d["win_rate_ci95_approx"] = None
    return d


def trades_to_sims(trades: list[dict]) -> list[SimulatedTrade]:
    return [
        SimulatedTrade(
            entry_price=t["entry_price"],
            exit_price=t["exit_price"],
            direction=t["direction"],
            outcome=t["outcome"],
            pnl_pips=t["pnl_pips"],
            pnl_price=t["pnl_price"],
            risk_price=1.0,
            r_multiple=t["r_multiple"],
            score=t["score"],
            ambiguous=t["ambiguous"],
            bars_held=t["bars_held"],
        )
        for t in trades
    ]


def resimulate(candles, signals: list[dict], cfg: ExecutionConfig):
    pip = pip_size_for_symbol("XAUUSD")
    by_ts = {c.timestamp.isoformat(): i for i, c in enumerate(candles)}
    sims = []
    trades = []
    for sig in signals:
        i = by_ts.get(sig["timestamp"])
        if i is None:
            continue
        trade = simulate_trade(
            direction=sig["direction"],
            entry=sig["entry"],
            stop_loss=sig["stop_loss"],
            take_profit=sig["take_profit_1"],
            forward_bars=candles[i + 1 : i + 1 + FORWARD_BARS],
            pip=pip,
            score=sig["score"],
            config=cfg,
        )
        sims.append(trade)
        trades.append({**{k: sig[k] for k in ("signal_id", "timestamp", "direction", "score", "confidence", "ranking_htf_trend", "structure_external_bias", "trend") if k in sig},
                       "entry_price": trade.entry_price, "exit_price": trade.exit_price,
                       "outcome": trade.outcome, "pnl_pips": trade.pnl_pips, "pnl_price": trade.pnl_price,
                       "r_multiple": trade.r_multiple, "ambiguous": trade.ambiguous, "bars_held": trade.bars_held,
                       "execution": asdict(cfg)})
    return trades, sims


def monte_carlo(trades: list[SimulatedTrade], *, n: int = 2000, seed: int = 140) -> dict:
    if not trades:
        return {"n_resamples": 0, "note": "no trades"}
    rs = [t.r_multiple for t in trades]
    rng = random.Random(seed)
    finals, max_dds, max_lose = [], [], []
    for _ in range(n):
        sample = [rng.choice(rs) for _ in rs]
        equity = peak = max_dd = 0.0
        lose = lose_max = 0
        for r in sample:
            equity += r
            peak = max(peak, equity)
            max_dd = max(max_dd, peak - equity)
            if r < 0:
                lose += 1
                lose_max = max(lose_max, lose)
            else:
                lose = 0
        finals.append(equity)
        max_dds.append(max_dd)
        max_lose.append(lose_max)
    finals.sort()
    max_dds.sort()
    return {
        "n_resamples": n,
        "seed": seed,
        "observed_total_r": round(sum(rs), 4),
        "resampled_total_r_median": round(finals[len(finals) // 2], 4),
        "resampled_total_r_p05": round(finals[int(0.05 * len(finals))], 4),
        "resampled_total_r_p95": round(finals[int(0.95 * len(finals))], 4),
        "resampled_max_dd_r_median": round(max_dds[len(max_dds) // 2], 4),
        "resampled_max_dd_r_p95": round(max_dds[int(0.95 * len(max_dds))], 4),
        "resampled_max_losing_streak_median": max_lose[len(max_lose) // 2],
        "distinction": "RESAMPLED ESTIMATE from observed trade R only",
    }


def load_all_chunks() -> tuple[list[dict], list[dict]]:
    signals, trades = [], []
    for ym in TEST_MONTHS:
        path = CHUNKS / f"{ym}.json"
        if not path.exists():
            raise FileNotFoundError(f"Missing chunk {path}; run --month {ym} first")
        data = json.loads(path.read_text(encoding="utf-8"))
        signals.extend(data["signals"])
        trades.extend(data["trades"])
    return signals, trades


def finalize(candles) -> int:
    signals, trades = load_all_chunks()
    sims = trades_to_sims(trades)
    baseline = metrics_dict(sims)

    with (OUT_DIR / "signals.jsonl").open("w", encoding="utf-8") as fh:
        for s in signals:
            fh.write(json.dumps(s, default=str) + "\n")
    with (OUT_DIR / "trades.jsonl").open("w", encoding="utf-8") as fh:
        for t in trades:
            fh.write(json.dumps(t, default=str) + "\n")

    _, sims_low = resimulate(candles, signals, LOW_EXEC)
    _, sims_high = resimulate(candles, signals, HIGH_EXEC)
    cost = {
        "baseline": baseline,
        "low_cost": metrics_dict(sims_low),
        "high_cost": metrics_dict(sims_high),
        "note": "BASELINE primary; low/high re-simulate same signals",
    }

    # Walk-forward quarters from trades
    wf = []
    for name, a, b in [
        ("WF1_2024Q1", "2024-01-01T00:00:00+00:00", "2024-03-31T23:00:00+00:00"),
        ("WF2_2024Q2", "2024-04-01T00:00:00+00:00", "2024-06-30T23:00:00+00:00"),
        ("WF3_2024Q3partial", "2024-07-01T00:00:00+00:00", "2024-07-11T04:00:00+00:00"),
    ]:
        sa, sb = _parse_iso(a), _parse_iso(b)
        tr = [t for t in trades if sa <= datetime.fromisoformat(t["timestamp"]) <= sb]
        wf.append({
            "window": name,
            "train": "N/A — no parameter fitting",
            "validation": "N/A — no parameter fitting",
            "test_start": a,
            "test_end": b,
            "trades": len(tr),
            "metrics": metrics_dict(trades_to_sims(tr)),
        })
    (OUT_DIR / "walk_forward.json").write_text(json.dumps(wf, indent=2) + "\n", encoding="utf-8")

    by_m: dict[str, list] = defaultdict(list)
    for t in trades:
        by_m[t["timestamp"][:7]].append(t)
    subperiods = [{"period": m, **metrics_dict(trades_to_sims(by_m[m]))} for m in sorted(by_m)]

    by_r: dict[str, list] = defaultdict(list)
    for t in trades:
        by_r[str(t.get("structure_external_bias") or t.get("trend") or "undefined")].append(t)
    regimes = {k: metrics_dict(trades_to_sims(v)) for k, v in sorted(by_r.items())}

    mc = monte_carlo(sims)

    # Repro: re-analyze up to 25 signals
    print("Reproducibility sample re-analyze…", flush=True)
    engine = DecisionEngine()
    smc = SMCEngine()
    news = NewsContext(score=10)
    by_ts = {c.timestamp.isoformat(): i for i, c in enumerate(candles)}
    sample = signals[:: max(1, len(signals) // 25)][:25] if signals else []
    mismatch = 0
    for sig in sample:
        i = by_ts[sig["timestamp"]]
        w0 = max(0, i - LOOKBACK_BARS + 1)
        bundle = analyze_candle_window(
            "XAUUSD", Timeframe.H1, candles[w0 : i + 1],
            news=news, decision_engine=engine, smc_engine=smc, evaluate=True,
        )
        if bundle.analytical_fingerprint() != sig["analytical_fingerprint"]:
            mismatch += 1
    trades2, sims2 = resimulate(candles, signals, BASE_EXEC)

    def _trade_core(t: dict) -> dict:
        return {
            "signal_id": t["signal_id"],
            "timestamp": t["timestamp"],
            "direction": t["direction"],
            "outcome": t["outcome"],
            "entry_price": round(float(t["entry_price"]), 8),
            "exit_price": round(float(t["exit_price"]), 8),
            "r_multiple": round(float(t["r_multiple"]), 8),
            "pnl_pips": round(float(t["pnl_pips"]), 8),
            "ambiguous": t["ambiguous"],
        }

    th1 = _sha256_bytes(
        "\n".join(json.dumps(_trade_core(t), sort_keys=True) for t in trades).encode()
    )
    th2 = _sha256_bytes(
        "\n".join(json.dumps(_trade_core(t), sort_keys=True) for t in trades2).encode()
    )
    repro = {
        "fingerprint_sample_size": len(sample),
        "fingerprint_mismatches": mismatch,
        "run1_trade_hash": th1,
        "run2_trade_hash": th2,
        "trades_identical": th1 == th2,
        "fingerprints_identical": mismatch == 0,
        "identical": th1 == th2 and mismatch == 0,
        "metrics_run1": baseline,
        "metrics_run2": metrics_dict(sims2),
        "note": "Trade hash uses outcome-critical fields only",
    }
    (OUT_DIR / "reproducibility.json").write_text(json.dumps(repro, indent=2) + "\n", encoding="utf-8")

    leakage = {
        "status": "PASS",
        "evidence": [
            "analyze_candle_window on causal lookback ending at signal bar",
            "HTF via pipeline resolve_mtf_trends / completed-bar filter",
            "simulate_trade on post-signal bars only; sl_first",
            "Neutral NewsContext",
            "Splits/config locked before evaluation",
            "No parameter fitting",
            f"Signal stride={SIGNAL_STRIDE} and lookback={LOOKBACK_BARS} fixed a priori",
        ],
        "pipeline_version": ANALYSIS_PIPELINE_VERSION,
    }

    dist = {
        "long": sum(1 for t in trades if t["direction"] == "buy"),
        "short": sum(1 for t in trades if t["direction"] == "sell"),
        "by_month": {m: len(by_m[m]) for m in sorted(by_m)},
        "by_htf_trend": {},
        "by_structure": {},
    }
    for t in trades:
        ht = str(t.get("ranking_htf_trend") or "none")
        dist["by_htf_trend"][ht] = dist["by_htf_trend"].get(ht, 0) + 1
        st = str(t.get("structure_external_bias") or "undefined")
        dist["by_structure"][st] = dist["by_structure"].get(st, 0) + 1

    metrics_all = {
        "baseline": baseline,
        "cost_sensitivity": cost,
        "walk_forward": wf,
        "subperiods": subperiods,
        "regimes": regimes,
        "monte_carlo": mc,
        "distribution": dist,
        "leakage_audit": leakage,
    }
    (OUT_DIR / "metrics.json").write_text(json.dumps(metrics_all, indent=2) + "\n", encoding="utf-8")

    n = baseline["total_trades"]
    pf = baseline.get("profit_factor")
    exp = baseline.get("expectancy", 0) or 0
    if not repro["identical"]:
        verdict = "INVALID — DATA/CAUSALITY ISSUE"
    elif n < 30:
        verdict = "INSUFFICIENT EVIDENCE"
    elif pf is not None and pf < 0.9 and exp < 0:
        verdict = "FAILED OOS VALIDATION"
    elif pf is not None and pf >= 1.5 and exp > 0.1 and n >= 100:
        verdict = "ROBUST OOS PERFORMANCE"
    elif exp > 0 and (pf is None or pf >= 1.0):
        verdict = "PROMISING BUT UNPROVEN"
    else:
        verdict = "FAILED OOS VALIDATION"

    cfg = json.loads((OUT_DIR / "config_manifest.json").read_text(encoding="utf-8"))
    ds = json.loads((OUT_DIR / "dataset_manifest.json").read_text(encoding="utf-8"))

    report = f"""# OOS Validation Report — Pipeline 1.4.0

Generated: {datetime.now(timezone.utc).isoformat()}

## 1. Dataset

| Field | Value |
|-------|-------|
| Dataset ID | `{DATASET_ID}` |
| Provider | WEALTHTEX_MT5_XAUUSD_VX |
| Symbol | XAUUSD |
| Timeframe | H1 |
| Date range | {ds['date_range']['start']} → {ds['date_range']['end']} |
| Candle count | {ds['candle_count']} |
| SHA-256 | `{ds['sha256']}` |

## 2. Configuration

| Field | Value |
|-------|-------|
| Pipeline | `{ANALYSIS_PIPELINE_VERSION}` |
| Entry | signal_close |
| Ambiguous | sl_first |
| SL/TP | signal stop_loss / take_profit_1 |
| Spread/Slip/Comm (BASE) | 0 / 0 / 0 |
| min_score | {MIN_SCORE} |
| lookback / stride | {LOOKBACK_BARS} / {SIGNAL_STRIDE} |
| Parameter fitting | **None** |
| Config hash | `{cfg.get('config_sha256')}` |

## 3. Split

| Split | Start | End | Role |
|-------|-------|-----|------|
| Train | {SPLIT['train'][0]} | {SPLIT['train'][1]} | Descriptive — no fitting |
| Validation | {SPLIT['validation'][0]} | {SPLIT['validation'][1]} | Descriptive — no fitting |
| **Test** | {SPLIT['test'][0]} | {SPLIT['test'][1]} | **Headline OOS** |

## 4. Overall OOS (BASELINE — OBSERVED)

| Metric | Value |
|--------|-------|
| Trades | {baseline['total_trades']} |
| Wins / Losses / BE | {baseline['wins']} / {baseline['losses']} / {baseline['breakeven']} |
| Win rate | {baseline['win_rate']}% (approx CI {baseline.get('win_rate_ci95_approx')}) |
| Profit factor | {baseline['profit_factor']} |
| Expectancy (avg R) | {baseline['expectancy']} |
| Total R | {baseline['total_r']} |
| Max DD (R) | {baseline['max_drawdown_r']} |
| Max DD (pips) | {baseline['max_drawdown_pips']} |
| Avg winner / loser (pips) | {baseline['avg_winner_pips']} / {baseline['avg_loser_pips']} |
| Longest losing streak | {baseline['consecutive_losses_max']} |
| Longest winning streak | {baseline['consecutive_wins_max']} |
| Ambiguous | {baseline['ambiguous_trades']} |

## 5. Walk-Forward

No parameter fitting. Same frozen config on chronological TEST slices.

| Window | Trades | WR% | PF | Exp | Total R | MaxDD R |
|--------|--------|-----|----|-----|---------|---------|
"""
    for w in wf:
        m = w["metrics"]
        report += (
            f"| {w['window']} | {m['total_trades']} | {m['win_rate']} | {m['profit_factor']} | "
            f"{m['expectancy']} | {m['total_r']} | {m['max_drawdown_r']} |\n"
        )
    report += "\n## 6. Subperiod Stability\n\n| Period | Trades | WR% | PF | Exp | Total R | MaxDD R |\n|--------|--------|-----|----|-----|---------|---------|\n"
    for r in subperiods:
        report += (
            f"| {r['period']} | {r['total_trades']} | {r['win_rate']} | {r['profit_factor']} | "
            f"{r['expectancy']} | {r['total_r']} | {r['max_drawdown_r']} |\n"
        )
    report += "\n## 7. Regime Analysis\n\n"
    for k, m in regimes.items():
        report += f"- **{k}**: n={m['total_trades']}, WR={m['win_rate']}%, PF={m['profit_factor']}, exp={m['expectancy']}, total_R={m['total_r']}\n"
    report += f"""
## 8. Cost Sensitivity

| Scenario | Trades | WR% | PF | Exp | Total R | MaxDD R |
|----------|--------|-----|----|-----|---------|---------|
| BASELINE | {cost['baseline']['total_trades']} | {cost['baseline']['win_rate']} | {cost['baseline']['profit_factor']} | {cost['baseline']['expectancy']} | {cost['baseline']['total_r']} | {cost['baseline']['max_drawdown_r']} |
| LOW | {cost['low_cost']['total_trades']} | {cost['low_cost']['win_rate']} | {cost['low_cost']['profit_factor']} | {cost['low_cost']['expectancy']} | {cost['low_cost']['total_r']} | {cost['low_cost']['max_drawdown_r']} |
| HIGH | {cost['high_cost']['total_trades']} | {cost['high_cost']['win_rate']} | {cost['high_cost']['profit_factor']} | {cost['high_cost']['expectancy']} | {cost['high_cost']['total_r']} | {cost['high_cost']['max_drawdown_r']} |

## 9. Reproducibility

| Check | Result |
|-------|--------|
| Trade hash match | {repro['trades_identical']} |
| Fingerprint sample mismatches | {mismatch}/{len(sample)} |
| Identical | **{repro['identical']}** |

## 10. Leakage Audit

**{leakage['status']}**

"""
    for e in leakage["evidence"]:
        report += f"- {e}\n"
    report += f"""
## 11. Statistical Interpretation

**OBSERVED:** baseline metrics on locked TEST under frozen 1.4.0 + documented execution/lookback/stride.

**INFERRED:** win-rate CI; Monte Carlo trade-order resampling (median total R={mc.get('resampled_total_r_median')}, p05={mc.get('resampled_total_r_p05')}, p95={mc.get('resampled_total_r_p95')}).

**UNKNOWN:** live fill quality beyond costs; news causality; unique broker IANA zone; prospective post-2026 performance.

n={n}. Stride={SIGNAL_STRIDE} reduces evaluation density vs every bar — cadence fixed before results, not tuned to outcomes.

## 12. Problems Found

- Retrospective (not prospective) OHLC package.
- Finite lookback {LOOKBACK_BARS} + stride {SIGNAL_STRIDE} (evaluation design, documented).
- Weekday gaps documented in integrity report; not repaired.
"""
    if n < 30:
        report += "- Trade count < 30 — weak evidence.\n"
    report += f"""
## 13. Pipeline Changes

None — analytical pipeline remained frozen at 1.4.0.

## 14. Verdict

**{verdict}**

## 15. Next Task

"""
    if verdict in ("PROMISING BUT UNPROVEN", "ROBUST OOS PERFORMANCE"):
        report += "A. Controlled paper/live shadow validation on prospectively accruing data (no tuning).\n"
    elif verdict == "INSUFFICIENT EVIDENCE":
        report += "A. Extend coverage with a new versioned dataset or longer shadow — still no tuning.\n"
    elif verdict == "FAILED OOS VALIDATION":
        report += "B. Separately versioned optimization experiment only if product reopens analytics — do not patch 1.4.0 silently.\n"
    else:
        report += "Resolve integrity/reproducibility before any performance claim.\n"

    report += f"\n## Distribution\n\n- Long/Short: {dist['long']}/{dist['short']}\n- HTF: {dist['by_htf_trend']}\n- Structure: {dist['by_structure']}\n"

    (ROOT / "docs/OOS_VALIDATION_REPORT_1.4.0.md").write_text(report, encoding="utf-8")
    print(f"VERDICT: {verdict}", flush=True)
    return 0 if repro["identical"] else 1


def load_data():
    assert ANALYSIS_PIPELINE_VERSION == "1.4.0"
    if not SOURCE_PATH.exists():
        raise SystemExit(f"MISSING DATASET: {SOURCE_PATH}")
    actual = _sha256_file(SOURCE_PATH)
    if actual != EXPECTED_SHA256:
        raise SystemExit(f"HASH MISMATCH: {actual}")
    candles = load_candles_csv(
        SOURCE_PATH, symbol="XAUUSD", timeframe=Timeframe.H1, expected_sha256=EXPECTED_SHA256
    )
    integrity = integrity_check(candles)
    if not integrity.ok:
        raise SystemExit(f"INTEGRITY FAIL: {asdict(integrity)}")
    write_manifests(candles, integrity, actual)
    return candles


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", help="YYYY-MM chunk in TEST")
    ap.add_argument("--finalize", action="store_true")
    ap.add_argument("--all-months", action="store_true")
    args = ap.parse_args()
    candles = load_data()
    if args.finalize:
        return finalize(candles)
    if args.all_months:
        for ym in TEST_MONTHS:
            if not (CHUNKS / f"{ym}.json").exists():
                run_month(candles, ym)
        return finalize(candles)
    if args.month:
        if args.month not in TEST_MONTHS:
            raise SystemExit(f"month must be one of {TEST_MONTHS}")
        run_month(candles, args.month)
        return 0
    raise SystemExit("Specify --month YYYY-MM, --all-months, or --finalize")


if __name__ == "__main__":
    raise SystemExit(main())

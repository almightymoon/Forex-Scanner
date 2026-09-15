#!/usr/bin/env python3
"""Pipeline 1.5.0 Arm H1 — score/confidence emit calibration experiment.

Hard rules:
  - Frozen 1.4.0 analysis unchanged (DecisionEngine / ranking / zones).
  - Fit & select ONLY on TRAIN (2022) + VALIDATION (2023).
  - Lock selection to disk BEFORE reading TEST metrics.
  - TEST uses locked 1.4.0 OOS trades from validation/ filtered by the gate
    (same OHLC, same signals — only emit policy differs).

Usage:
  python scripts/run_oos_experiment_1_5_0.py --generate-fit   # TRAIN+VAL corpora
  python scripts/run_oos_experiment_1_5_0.py --select         # lock policy (no TEST)
  python scripts/run_oos_experiment_1_5_0.py --test           # TEST once after lock
  python scripts/run_oos_experiment_1_5_0.py --finalize       # write report artifacts
  python scripts/run_oos_experiment_1_5_0.py --all            # generate → select → test → finalize
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
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
from services.quant_engine.pipeline.calibration_1_5_0 import (
    BASELINE_1_4_0_TEST,
    CANDIDATE_POLICIES,
    DEFAULT_SELECTION,
    DEFAULT_TEST_SUCCESS,
    EXPERIMENT_ARM,
    EXPERIMENT_PIPELINE_VERSION,
    EmitPolicy,
    evaluate_test_success,
    filter_trades,
    select_policy,
)
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
TRAIN_MONTHS = [f"2022-{m:02d}" for m in range(1, 13)]
VAL_MONTHS = [f"2023-{m:02d}" for m in range(1, 13)]
LOOKBACK_BARS = 250
SIGNAL_STRIDE = 4
MIN_SCORE = 70
FORWARD_BARS = 20
COOLDOWN = FORWARD_BARS // 2
BASE_EXEC = ExecutionConfig("signal_close", "sl_first", 0.0, 0.0, 0.0)

OUT_DIR = ROOT / "validation_1_5_0"
FIT_CHUNKS = OUT_DIR / "fit_chunks"
BASELINE_VALIDATION = ROOT / "validation"


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
        d["expectancy"] = 0.0
        d["profit_factor"] = 0.0
        d["win_rate"] = 0.0
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


def metrics_from_trade_dicts(trades: list[dict]) -> dict[str, Any]:
    if not trades:
        return metrics_dict([])
    return metrics_dict(trades_to_sims(trades))


def split_for_month(ym: str) -> str:
    y = int(ym.split("-")[0])
    if y == 2022:
        return "train"
    if y == 2023:
        return "validation"
    return "test"


def month_bounds(ym: str) -> tuple[datetime, datetime]:
    y, m = map(int, ym.split("-"))
    start = datetime(y, m, 1, 0, 0, tzinfo=timezone.utc)
    if m == 12:
        next_m = datetime(y + 1, 1, 1, 0, 0, tzinfo=timezone.utc)
    else:
        next_m = datetime(y, m + 1, 1, 0, 0, tzinfo=timezone.utc)
    split_name = split_for_month(ym)
    split_start = _parse_iso(SPLIT[split_name][0])
    split_end = _parse_iso(SPLIT[split_name][1])
    start = max(start, split_start)
    end_inclusive = min(next_m - timedelta(hours=1), split_end)
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
        if (i - start_i) % 240 == 0:
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
            "pipeline_version": ANALYSIS_PIPELINE_VERSION,
            "experiment_pipeline_version": EXPERIMENT_PIPELINE_VERSION,
            "direction": signal.direction.value,
            "score": signal.score,
            "confidence": signal.confidence,
            "entry": window[-1].close,
            "stop_loss": signal.stop_loss,
            "take_profit_1": signal.take_profit_1,
            "month": ym,
            "split": split_for_month(ym),
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
                "entry_price": trade.entry_price,
                "exit_price": trade.exit_price,
                "outcome": trade.outcome,
                "pnl_pips": trade.pnl_pips,
                "pnl_price": trade.pnl_price,
                "r_multiple": trade.r_multiple,
                "ambiguous": trade.ambiguous,
                "bars_held": trade.bars_held,
                "month": ym,
                "split": split_for_month(ym),
                "execution": asdict(BASE_EXEC),
            }
        )
        cooldown = COOLDOWN

    elapsed = time.perf_counter() - t0
    out = {
        "month": ym,
        "split": split_for_month(ym),
        "start": start.isoformat(),
        "end": end.isoformat(),
        "runtime_seconds": round(elapsed, 2),
        "signals": signals,
        "trades": trades,
        "metrics": metrics_dict(sims),
    }
    FIT_CHUNKS.mkdir(parents=True, exist_ok=True)
    path = FIT_CHUNKS / f"{ym}.json"
    path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(
        f"  wrote {path.name}: signals={len(signals)} trades={len(trades)} in {elapsed:.1f}s",
        flush=True,
    )
    return out


def load_fit_trades(split: str) -> list[dict]:
    trades: list[dict] = []
    months = TRAIN_MONTHS if split == "train" else VAL_MONTHS
    for ym in months:
        path = FIT_CHUNKS / f"{ym}.json"
        if not path.exists():
            raise FileNotFoundError(f"missing fit chunk {path}; run --generate-fit first")
        payload = json.loads(path.read_text(encoding="utf-8"))
        trades.extend(payload.get("trades") or [])
    return trades


def load_baseline_test_trades() -> list[dict]:
    path = BASELINE_VALIDATION / "trades.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"missing locked 1.4.0 trades at {path}")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def generate_fit(candles) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    actual = _sha256_file(SOURCE_PATH)
    if actual != EXPECTED_SHA256:
        raise SystemExit(f"dataset hash mismatch: {actual} != {EXPECTED_SHA256}")
    for ym in TRAIN_MONTHS + VAL_MONTHS:
        path = FIT_CHUNKS / f"{ym}.json"
        if path.exists():
            print(f"skip existing {path.name}", flush=True)
            continue
        run_month(candles, ym)
    # Aggregate fit corpora (no TEST)
    train_trades = load_fit_trades("train")
    val_trades = load_fit_trades("validation")
    (OUT_DIR / "fit_train_trades.jsonl").write_text(
        "".join(json.dumps(t) + "\n" for t in train_trades), encoding="utf-8"
    )
    (OUT_DIR / "fit_validation_trades.jsonl").write_text(
        "".join(json.dumps(t) + "\n" for t in val_trades), encoding="utf-8"
    )
    summary = {
        "train_trades": len(train_trades),
        "validation_trades": len(val_trades),
        "dataset_sha256": actual,
        "baseline_analysis_version": ANALYSIS_PIPELINE_VERSION,
        "experiment_version": EXPERIMENT_PIPELINE_VERSION,
        "arm": EXPERIMENT_ARM,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    (OUT_DIR / "fit_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


def run_select() -> dict:
    """Lock selection from VALIDATION only. Refuses if selection.json already implies TEST peek."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    selection_path = OUT_DIR / "selection.json"
    if (OUT_DIR / "test_metrics.json").exists():
        raise SystemExit("test_metrics.json already exists — selection must precede TEST")

    train_trades = load_fit_trades("train")
    val_trades = load_fit_trades("validation")

    train_by_policy: dict[str, dict] = {}
    val_by_policy: dict[str, dict] = {}
    for policy in CANDIDATE_POLICIES:
        train_by_policy[policy.name] = metrics_from_trade_dicts(filter_trades(train_trades, policy))
        val_by_policy[policy.name] = metrics_from_trade_dicts(filter_trades(val_trades, policy))

    selection = select_policy(val_by_policy, criteria=DEFAULT_SELECTION)
    payload = {
        "locked_at": datetime.now(timezone.utc).isoformat(),
        "experiment_version": EXPERIMENT_PIPELINE_VERSION,
        "arm": EXPERIMENT_ARM,
        "baseline_analysis_version": ANALYSIS_PIPELINE_VERSION,
        "selection_criteria": asdict(DEFAULT_SELECTION),
        "test_success_criteria": asdict(DEFAULT_TEST_SUCCESS),
        "candidates": [p.to_dict() for p in CANDIDATE_POLICIES],
        "train_metrics_by_policy": train_by_policy,
        "validation_metrics_by_policy": val_by_policy,
        "selection": selection,
        "test_not_evaluated_yet": True,
        "notes": [
            "Selection used VALIDATION metrics only.",
            "TRAIN metrics logged for transparency; not used in selection key.",
            "TEST must not be read until this file is written.",
        ],
    }
    raw = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    payload["selection_sha256"] = _sha256_bytes(raw.encode())
    selection_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {selection_path}", flush=True)
    print(
        f"qualified={selection['qualified']} selected={selection.get('selected')}",
        flush=True,
    )
    return payload


def run_test() -> dict:
    selection_path = OUT_DIR / "selection.json"
    if not selection_path.exists():
        raise SystemExit("selection.json missing — run --select before --test")
    if (OUT_DIR / "test_metrics.json").exists():
        raise SystemExit("TEST already evaluated (test_metrics.json exists) — one shot only")

    selection_doc = json.loads(selection_path.read_text(encoding="utf-8"))
    sel = selection_doc["selection"]
    if not sel.get("qualified") or not sel.get("selected"):
        # Still evaluate diagnostic-best for the report, labeled failed selection.
        if not sel.get("selected"):
            raise SystemExit("no selected policy to evaluate")

    policy = EmitPolicy(**sel["selected"])
    baseline_trades = load_baseline_test_trades()
    filtered = filter_trades(baseline_trades, policy)
    metrics = metrics_from_trade_dicts(filtered)
    success = evaluate_test_success(metrics, criteria=DEFAULT_TEST_SUCCESS, baseline=BASELINE_1_4_0_TEST)

    # Tag emitted signals for the experiment version
    signals = []
    for t in filtered:
        signals.append(
            {
                "signal_id": t["signal_id"],
                "timestamp": t["timestamp"],
                "direction": t["direction"],
                "score": t["score"],
                "confidence": t["confidence"],
                "pipeline_version": EXPERIMENT_PIPELINE_VERSION,
                "baseline_analysis_version": ANALYSIS_PIPELINE_VERSION,
                "emit_policy": policy.name,
                "month": t.get("month"),
            }
        )

    (OUT_DIR / "signals.jsonl").write_text(
        "".join(json.dumps(s) + "\n" for s in signals), encoding="utf-8"
    )
    (OUT_DIR / "trades.jsonl").write_text(
        "".join(json.dumps(t) + "\n" for t in filtered), encoding="utf-8"
    )
    test_doc = {
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "experiment_version": EXPERIMENT_PIPELINE_VERSION,
        "arm": EXPERIMENT_ARM,
        "emit_policy": policy.to_dict(),
        "selection_qualified": bool(sel.get("qualified")),
        "baseline_test_trades": len(baseline_trades),
        "filtered_test_trades": len(filtered),
        "metrics": metrics,
        "success": success,
        "baseline_1_4_0": BASELINE_1_4_0_TEST,
        "source_trades": str((BASELINE_VALIDATION / "trades.jsonl").relative_to(ROOT)),
        "note": (
            "TEST trades are the locked 1.4.0 OOS corpus filtered by the H1 emit policy; "
            "underlying analysis fingerprints unchanged."
        ),
    }
    (OUT_DIR / "test_metrics.json").write_text(json.dumps(test_doc, indent=2) + "\n", encoding="utf-8")

    # Mark selection as TEST-revealed
    selection_doc["test_not_evaluated_yet"] = False
    selection_doc["test_revealed_at"] = test_doc["evaluated_at"]
    selection_path.write_text(json.dumps(selection_doc, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({"policy": policy.name, "metrics": metrics, "success": success}, indent=2), flush=True)
    return test_doc


def finalize() -> None:
    selection_path = OUT_DIR / "selection.json"
    test_path = OUT_DIR / "test_metrics.json"
    if not selection_path.exists() or not test_path.exists():
        raise SystemExit("need selection.json and test_metrics.json")

    selection_doc = json.loads(selection_path.read_text(encoding="utf-8"))
    test_doc = json.loads(test_path.read_text(encoding="utf-8"))
    actual = _sha256_file(SOURCE_PATH)

    dataset_manifest = {
        "dataset_id": DATASET_ID,
        "sha256": actual,
        "expected_sha256": EXPECTED_SHA256,
        "hash_match": actual == EXPECTED_SHA256,
        "split": SPLIT,
        "source_path": str(SOURCE_PATH.relative_to(ROOT)),
        "pipeline_baseline": ANALYSIS_PIPELINE_VERSION,
        "experiment_version": EXPERIMENT_PIPELINE_VERSION,
        "arm": EXPERIMENT_ARM,
    }
    config_manifest = {
        "experiment_version": EXPERIMENT_PIPELINE_VERSION,
        "arm": EXPERIMENT_ARM,
        "baseline_analysis_version": ANALYSIS_PIPELINE_VERSION,
        "min_score_baseline_emit": MIN_SCORE,
        "lookback_bars": LOOKBACK_BARS,
        "signal_stride": SIGNAL_STRIDE,
        "forward_bars": FORWARD_BARS,
        "cooldown_bars": COOLDOWN,
        "execution": asdict(BASE_EXEC),
        "candidates": [p.to_dict() for p in CANDIDATE_POLICIES],
        "selection_criteria": asdict(DEFAULT_SELECTION),
        "test_success_criteria": asdict(DEFAULT_TEST_SUCCESS),
        "selected_policy": test_doc.get("emit_policy"),
        "parameter_fitting": "discrete_policy_selection_on_validation_only",
    }
    config_manifest["config_sha256"] = _sha256_bytes(
        json.dumps(config_manifest, sort_keys=True).encode()
    )

    metrics = {
        "BASE": test_doc["metrics"],
        "success": test_doc["success"],
        "selection_qualified": test_doc["selection_qualified"],
        "baseline_1_4_0": BASELINE_1_4_0_TEST,
    }
    walk_forward = {
        "train_metrics_by_policy": selection_doc.get("train_metrics_by_policy"),
        "validation_metrics_by_policy": selection_doc.get("validation_metrics_by_policy"),
        "selection": selection_doc.get("selection"),
    }
    reproducibility = {
        "dataset_sha256": actual,
        "selection_sha256": selection_doc.get("selection_sha256"),
        "config_sha256": config_manifest["config_sha256"],
        "baseline_trades_path": "validation/trades.jsonl",
        "analysis_version_for_signals": ANALYSIS_PIPELINE_VERSION,
        "emit_version": EXPERIMENT_PIPELINE_VERSION,
    }

    (OUT_DIR / "dataset_manifest.json").write_text(
        json.dumps(dataset_manifest, indent=2) + "\n", encoding="utf-8"
    )
    (OUT_DIR / "config_manifest.json").write_text(
        json.dumps(config_manifest, indent=2) + "\n", encoding="utf-8"
    )
    (OUT_DIR / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    (OUT_DIR / "walk_forward.json").write_text(
        json.dumps(walk_forward, indent=2) + "\n", encoding="utf-8"
    )
    (OUT_DIR / "reproducibility.json").write_text(
        json.dumps(reproducibility, indent=2) + "\n", encoding="utf-8"
    )

    m = test_doc["metrics"]
    success = test_doc["success"]
    sel = selection_doc["selection"]
    verdict = (
        "PASSED EXPERIMENT SUCCESS CRITERIA"
        if success.get("passed") and test_doc["selection_qualified"]
        else "FAILED EXPERIMENT"
    )
    report = f"""# Experiment Report — Pipeline {EXPERIMENT_PIPELINE_VERSION} (Arm {EXPERIMENT_ARM})

**Status:** {verdict}  
**Generated:** {datetime.now(timezone.utc).isoformat()}

## Predeclared design

| Field | Value |
|-------|-------|
| Arm | {EXPERIMENT_ARM} — score/confidence emit calibration |
| Baseline analysis | `{ANALYSIS_PIPELINE_VERSION}` (unchanged) |
| Experiment version | `{EXPERIMENT_PIPELINE_VERSION}` (emit gate only) |
| Dataset | `{DATASET_ID}` |
| Hash | `{actual}` |
| Fit | TRAIN 2022 / VALIDATION 2023 |
| TEST | 2024-01-01 → 2024-07-11 (once) |
| Cadence | lookback={LOOKBACK_BARS}, stride={SIGNAL_STRIDE}, min_score={MIN_SCORE} |

### Selection criteria (VALIDATION)

- expectancy ≥ {DEFAULT_SELECTION.min_expectancy}
- profit factor ≥ {DEFAULT_SELECTION.min_profit_factor}
- trades ≥ {DEFAULT_SELECTION.min_trades}

### TEST success criteria

- positive expectancy
- profit factor ≥ {DEFAULT_TEST_SUCCESS.require_pf_at_least}
- total R ≥ baseline ({BASELINE_1_4_0_TEST['total_r']}) − {DEFAULT_TEST_SUCCESS.max_total_r_worse_than_baseline}

## Selection (locked before TEST)

| Field | Value |
|-------|-------|
| Qualified | {sel.get('qualified')} |
| Selected | `{sel.get('selected', {}).get('name') if sel.get('selected') else None}` |
| Reason | {sel.get('reason')} |

VALIDATION metrics for selected policy:

```json
{json.dumps(sel.get('validation_metrics'), indent=2)}
```

## TEST results (observed once)

| Metric | 1.5.0 H1 | 1.4.0 BASE |
|--------|----------|------------|
| Trades | {m.get('total_trades')} | {BASELINE_1_4_0_TEST['trades']} |
| Win rate | {m.get('win_rate')} | {BASELINE_1_4_0_TEST['win_rate']} |
| Profit factor | {m.get('profit_factor')} | {BASELINE_1_4_0_TEST['profit_factor']} |
| Expectancy | {m.get('expectancy')} | {BASELINE_1_4_0_TEST['expectancy']} |
| Total R | {m.get('total_r')} | {BASELINE_1_4_0_TEST['total_r']} |

Success checks:

```json
{json.dumps(success, indent=2)}
```

## OBSERVED / INFERRED / UNKNOWN

**OBSERVED:** Emit-filtered TEST metrics above; selection used VALIDATION only; 1.4.0 analytical
code paths untouched.

**INFERRED:** {'Gate met predeclared success' if success.get('passed') and test_doc['selection_qualified'] else 'H1 emit calibration did not recover a validated edge under predeclared criteria'}.

**UNKNOWN:** Live fills, prospective generalization, whether other arms (H2/H3) would fare better.

## Non-claims

- Does not amend or rehabilitate frozen 1.4.0.
- Does not authorize silent score-weight tuning.
- Subgroup forensics remain exploratory; this arm tested only the predeclared candidate set.
"""
    report_path = ROOT / "docs" / "EXPERIMENT_REPORT_1.5.0.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"wrote {report_path}", flush=True)
    print(verdict, flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generate-fit", action="store_true")
    parser.add_argument("--select", action="store_true")
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--finalize", action="store_true")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--month", type=str, help="generate a single fit month YYYY-MM")
    args = parser.parse_args()

    if not any([args.generate_fit, args.select, args.test, args.finalize, args.all, args.month]):
        parser.error("specify an action")

    need_candles = args.generate_fit or args.all or args.month
    candles = None
    if need_candles:
        print(f"loading {SOURCE_PATH} ...", flush=True)
        candles = load_candles_csv(SOURCE_PATH, symbol="XAUUSD", timeframe=Timeframe.H1)
        print(f"loaded {len(candles)} candles", flush=True)

    if args.month:
        assert candles is not None
        run_month(candles, args.month)
        return
    if args.all or args.generate_fit:
        assert candles is not None
        generate_fit(candles)
    if args.all or args.select:
        run_select()
    if args.all or args.test:
        run_test()
    if args.all or args.finalize:
        finalize()


if __name__ == "__main__":
    main()

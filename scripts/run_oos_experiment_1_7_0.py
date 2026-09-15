#!/usr/bin/env python3
"""Pipeline 1.7.0 Arm H2 — exit / payoff geometry experiment.

Hard rules:
  - Frozen 1.4.0 signal generation unchanged (reuse fit + OOS signal corpora).
  - Only remap take-profit from original stop distance; SL stays fixed.
  - Select on VALIDATION only; TEST once after lock.

Usage:
  python scripts/run_oos_experiment_1_7_0.py --build
  python scripts/run_oos_experiment_1_7_0.py --select
  python scripts/run_oos_experiment_1_7_0.py --test
  python scripts/run_oos_experiment_1_7_0.py --finalize
  python scripts/run_oos_experiment_1_7_0.py --all
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.types.models import Timeframe
from services.backtesting_service.execution import (
    ExecutionConfig,
    SimulatedTrade,
    compute_performance_metrics,
    pip_size_for_symbol,
    simulate_trade,
)
from services.quant_engine.pipeline import ANALYSIS_PIPELINE_VERSION
from services.quant_engine.pipeline.calibration_1_7_0 import (
    BASELINE_1_4_0_TEST,
    CANDIDATE_POLICIES,
    DEFAULT_SELECTION,
    DEFAULT_TEST_SUCCESS,
    EXPERIMENT_ARM,
    EXPERIMENT_PIPELINE_VERSION,
    ExitPolicy,
    evaluate_test_success,
    select_policy,
)
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
FORWARD_BARS = 20
BASE_EXEC = ExecutionConfig("signal_close", "sl_first", 0.0, 0.0, 0.0)

FIT_CHUNKS = ROOT / "validation_1_5_0" / "fit_chunks"
BASELINE_VALIDATION = ROOT / "validation"
OUT_DIR = ROOT / "validation_1_7_0"
TRAIN_MONTHS = [f"2022-{m:02d}" for m in range(1, 13)]
VAL_MONTHS = [f"2023-{m:02d}" for m in range(1, 13)]


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
        d["expectancy"] = 0.0
        d["profit_factor"] = 0.0
        d["win_rate"] = 0.0
        d["win_rate_se_approx"] = None
        d["win_rate_ci95_approx"] = None
    return d


def load_fit_signals(months: list[str]) -> list[dict]:
    rows: list[dict] = []
    for ym in months:
        path = FIT_CHUNKS / f"{ym}.json"
        if not path.exists():
            raise FileNotFoundError(path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        for sig in payload.get("signals") or []:
            rows.append(dict(sig))
    return rows


def load_test_signals() -> list[dict]:
    path = BASELINE_VALIDATION / "signals.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def resim_signals(candles, signals: list[dict], policy: ExitPolicy) -> tuple[list[dict], dict]:
    pip = pip_size_for_symbol("XAUUSD")
    by_ts = {c.timestamp.isoformat(): i for i, c in enumerate(candles)}
    sims: list[SimulatedTrade] = []
    trades: list[dict] = []
    for sig in signals:
        i = by_ts.get(sig["timestamp"])
        if i is None:
            continue
        entry = float(sig["entry"])
        stop_loss = float(sig["stop_loss"])
        take_profit = float(sig["take_profit_1"])
        sl, tp = policy.levels(
            direction=sig["direction"],
            entry=entry,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )
        trade = simulate_trade(
            direction=sig["direction"],
            entry=entry,
            stop_loss=sl,
            take_profit=tp,
            forward_bars=candles[i + 1 : i + 1 + FORWARD_BARS],
            pip=pip,
            score=int(sig.get("score") or 0),
            config=BASE_EXEC,
        )
        sims.append(trade)
        trades.append(
            {
                "signal_id": sig["signal_id"],
                "timestamp": sig["timestamp"],
                "direction": sig["direction"],
                "score": sig.get("score"),
                "confidence": sig.get("confidence"),
                "entry_price": trade.entry_price,
                "stop_loss": sl,
                "take_profit": tp,
                "original_stop_loss": stop_loss,
                "original_take_profit": take_profit,
                "exit_policy": policy.name,
                "target_rr": policy.target_rr,
                "exit_price": trade.exit_price,
                "outcome": trade.outcome,
                "pnl_pips": trade.pnl_pips,
                "pnl_price": trade.pnl_price,
                "r_multiple": trade.r_multiple,
                "ambiguous": trade.ambiguous,
                "bars_held": trade.bars_held,
                "month": sig.get("month"),
                "split": sig.get("split"),
                "execution": asdict(BASE_EXEC),
            }
        )
    return trades, metrics_dict(sims)


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def run_build() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    actual = _sha256_file(SOURCE_PATH)
    if actual != EXPECTED_SHA256:
        raise SystemExit(f"dataset hash mismatch: {actual}")

    print(f"loading {SOURCE_PATH} ...", flush=True)
    candles = load_candles_csv(SOURCE_PATH, symbol="XAUUSD", timeframe=Timeframe.H1)
    print(f"loaded {len(candles)} candles", flush=True)

    train_sigs = load_fit_signals(TRAIN_MONTHS)
    val_sigs = load_fit_signals(VAL_MONTHS)
    print(f"signals train={len(train_sigs)} validation={len(val_sigs)}", flush=True)

    train_metrics: dict[str, dict] = {}
    val_metrics: dict[str, dict] = {}
    for policy in CANDIDATE_POLICIES:
        _, tm = resim_signals(candles, train_sigs, policy)
        _, vm = resim_signals(candles, val_sigs, policy)
        train_metrics[policy.name] = tm
        val_metrics[policy.name] = vm
        print(
            f"  {policy.name}: TRAIN exp={tm.get('expectancy')} n={tm.get('total_trades')} | "
            f"VAL exp={vm.get('expectancy')} n={vm.get('total_trades')}",
            flush=True,
        )

    payload = {
        "built_at": datetime.now(timezone.utc).isoformat(),
        "dataset_sha256": actual,
        "baseline_analysis_version": ANALYSIS_PIPELINE_VERSION,
        "experiment_version": EXPERIMENT_PIPELINE_VERSION,
        "arm": EXPERIMENT_ARM,
        "forward_bars": FORWARD_BARS,
        "candidates": [p.to_dict() for p in CANDIDATE_POLICIES],
        "train_signal_count": len(train_sigs),
        "validation_signal_count": len(val_sigs),
        "train_metrics_by_policy": train_metrics,
        "validation_metrics_by_policy": val_metrics,
        "notes": [
            "Signals reused from validation_1_5_0 fit chunks (1.4.0 analysis).",
            "Only take-profit remapped; stop_loss fixed at original level.",
        ],
    }
    (OUT_DIR / "fit_summary.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    # Persist baseline signal lists for TEST reproducibility / audit
    write_jsonl(OUT_DIR / "fit_train_signals.jsonl", train_sigs)
    write_jsonl(OUT_DIR / "fit_validation_signals.jsonl", val_sigs)
    print(f"wrote {OUT_DIR / 'fit_summary.json'}", flush=True)


def run_select() -> dict:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if (OUT_DIR / "test_metrics.json").exists():
        raise SystemExit("test_metrics.json already exists — selection must precede TEST")
    fit = json.loads((OUT_DIR / "fit_summary.json").read_text(encoding="utf-8"))
    selection = select_policy(fit["validation_metrics_by_policy"], criteria=DEFAULT_SELECTION)
    payload = {
        "locked_at": datetime.now(timezone.utc).isoformat(),
        "experiment_version": EXPERIMENT_PIPELINE_VERSION,
        "arm": EXPERIMENT_ARM,
        "baseline_analysis_version": ANALYSIS_PIPELINE_VERSION,
        "selection_criteria": asdict(DEFAULT_SELECTION),
        "test_success_criteria": asdict(DEFAULT_TEST_SUCCESS),
        "candidates": [p.to_dict() for p in CANDIDATE_POLICIES],
        "train_metrics_by_policy": fit["train_metrics_by_policy"],
        "validation_metrics_by_policy": fit["validation_metrics_by_policy"],
        "selection": selection,
        "test_not_evaluated_yet": True,
        "notes": [
            "Selection used VALIDATION metrics only.",
            "TRAIN metrics logged for transparency; not used in selection key.",
        ],
    }
    raw = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    payload["selection_sha256"] = _sha256_bytes(raw.encode())
    path = OUT_DIR / "selection.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {path}", flush=True)
    print(f"qualified={selection['qualified']} selected={selection.get('selected')}", flush=True)
    return payload


def run_test() -> dict:
    selection_path = OUT_DIR / "selection.json"
    if not selection_path.exists():
        raise SystemExit("selection.json missing")
    if (OUT_DIR / "test_metrics.json").exists():
        raise SystemExit("TEST already evaluated — one shot only")

    selection_doc = json.loads(selection_path.read_text(encoding="utf-8"))
    sel = selection_doc["selection"]
    if not sel.get("selected"):
        raise SystemExit("no selected policy")
    policy = ExitPolicy.from_dict(sel["selected"])

    actual = _sha256_file(SOURCE_PATH)
    if actual != EXPECTED_SHA256:
        raise SystemExit(f"dataset hash mismatch: {actual}")
    candles = load_candles_csv(SOURCE_PATH, symbol="XAUUSD", timeframe=Timeframe.H1)
    test_sigs = load_test_signals()
    trades, metrics = resim_signals(candles, test_sigs, policy)
    success = evaluate_test_success(metrics, criteria=DEFAULT_TEST_SUCCESS, baseline=BASELINE_1_4_0_TEST)

    write_jsonl(OUT_DIR / "trades.jsonl", trades)
    write_jsonl(
        OUT_DIR / "signals.jsonl",
        [
            {
                **{k: s.get(k) for k in ("signal_id", "timestamp", "direction", "score", "confidence", "entry", "month")},
                "pipeline_version": EXPERIMENT_PIPELINE_VERSION,
                "baseline_analysis_version": ANALYSIS_PIPELINE_VERSION,
                "exit_policy": policy.name,
                "target_rr": policy.target_rr,
            }
            for s in test_sigs
        ],
    )

    # Also report baseline remapped metrics for transparency (not selection)
    _, baseline_metrics = resim_signals(candles, test_sigs, ExitPolicy("h2_baseline_rr_133", None))

    test_doc = {
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "experiment_version": EXPERIMENT_PIPELINE_VERSION,
        "arm": EXPERIMENT_ARM,
        "exit_policy": policy.to_dict(),
        "selection_qualified": bool(sel.get("qualified")),
        "baseline_test_signals": len(test_sigs),
        "filtered_test_trades": len(trades),
        "metrics": metrics,
        "baseline_resim_metrics": baseline_metrics,
        "success": success,
        "baseline_1_4_0": BASELINE_1_4_0_TEST,
        "source_signals": "validation/signals.jsonl",
        "note": (
            "TEST uses locked 1.4.0 OOS signals with remapped TP under selected ExitPolicy; "
            "analysis fingerprints unchanged."
        ),
    }
    (OUT_DIR / "test_metrics.json").write_text(json.dumps(test_doc, indent=2) + "\n", encoding="utf-8")
    selection_doc["test_not_evaluated_yet"] = False
    selection_doc["test_revealed_at"] = test_doc["evaluated_at"]
    selection_path.write_text(json.dumps(selection_doc, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"policy": policy.name, "metrics": metrics, "success": success}, indent=2), flush=True)
    return test_doc


def finalize() -> None:
    selection_doc = json.loads((OUT_DIR / "selection.json").read_text(encoding="utf-8"))
    test_doc = json.loads((OUT_DIR / "test_metrics.json").read_text(encoding="utf-8"))
    actual = _sha256_file(SOURCE_PATH)
    sel = selection_doc["selection"]
    m = test_doc["metrics"]
    success = test_doc["success"]
    ranking = sel.get("ranking") or []
    rank_rows = "\n".join(
        f"| {r['name']} | {r.get('total_trades')} | {r.get('expectancy')} | {r.get('profit_factor')} | {r.get('total_r')} | {r.get('qualified')} |"
        for r in ranking
    )
    verdict = (
        "PASSED EXPERIMENT SUCCESS CRITERIA"
        if success.get("passed") and test_doc["selection_qualified"]
        else "FAILED EXPERIMENT"
    )
    selected_name = (sel.get("selected") or {}).get("name")

    dataset_manifest = {
        "dataset_id": DATASET_ID,
        "sha256": actual,
        "expected_sha256": EXPECTED_SHA256,
        "hash_match": actual == EXPECTED_SHA256,
        "split": SPLIT,
        "pipeline_baseline": ANALYSIS_PIPELINE_VERSION,
        "experiment_version": EXPERIMENT_PIPELINE_VERSION,
        "arm": EXPERIMENT_ARM,
    }
    config_manifest = {
        "experiment_version": EXPERIMENT_PIPELINE_VERSION,
        "arm": EXPERIMENT_ARM,
        "baseline_analysis_version": ANALYSIS_PIPELINE_VERSION,
        "forward_bars": FORWARD_BARS,
        "execution": asdict(BASE_EXEC),
        "candidates": [p.to_dict() for p in CANDIDATE_POLICIES],
        "selection_criteria": asdict(DEFAULT_SELECTION),
        "test_success_criteria": asdict(DEFAULT_TEST_SUCCESS),
        "selected_policy": test_doc.get("exit_policy"),
        "parameter_fitting": "discrete_tp_rr_on_validation_only",
        "mechanism": "keep original SL; remap TP to target_rr * risk (or baseline TP)",
    }
    config_manifest["config_sha256"] = _sha256_bytes(
        json.dumps(config_manifest, sort_keys=True).encode()
    )
    metrics = {
        "BASE": m,
        "baseline_resim": test_doc.get("baseline_resim_metrics"),
        "success": success,
        "selection_qualified": test_doc["selection_qualified"],
        "baseline_1_4_0": BASELINE_1_4_0_TEST,
    }
    walk_forward = {
        "train_metrics_by_policy": selection_doc.get("train_metrics_by_policy"),
        "validation_metrics_by_policy": selection_doc.get("validation_metrics_by_policy"),
        "selection": sel,
    }
    reproducibility = {
        "dataset_sha256": actual,
        "selection_sha256": selection_doc.get("selection_sha256"),
        "config_sha256": config_manifest["config_sha256"],
        "source_fit_chunks": "validation_1_5_0/fit_chunks",
        "source_test_signals": "validation/signals.jsonl",
        "analysis_version": ANALYSIS_PIPELINE_VERSION,
        "emit_version": EXPERIMENT_PIPELINE_VERSION,
    }
    for name, obj in [
        ("dataset_manifest.json", dataset_manifest),
        ("config_manifest.json", config_manifest),
        ("metrics.json", metrics),
        ("walk_forward.json", walk_forward),
        ("reproducibility.json", reproducibility),
    ]:
        (OUT_DIR / name).write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")

    report = f"""# Experiment Report — Pipeline {EXPERIMENT_PIPELINE_VERSION} (Arm {EXPERIMENT_ARM})

**Status:** {verdict}  
**Generated:** {datetime.now(timezone.utc).isoformat()}

## Predeclared design

| Field | Value |
|-------|-------|
| Arm | {EXPERIMENT_ARM} — exit / payoff geometry (TP remap) |
| Baseline analysis | `{ANALYSIS_PIPELINE_VERSION}` (unchanged) |
| Experiment version | `{EXPERIMENT_PIPELINE_VERSION}` |
| Mechanism | Keep original SL; set TP = entry ± target_rr × risk (or baseline TP) |
| Dataset hash | `{actual}` |
| Fit | TRAIN 2022 / VALIDATION 2023 |
| TEST | 2024-01-01 → 2024-07-11 (once) |
| Execution | signal_close / sl_first / costs 0 |

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
| Selected | `{selected_name}` |
| Reason | {sel.get('reason')} |

VALIDATION ranking:

| Policy | n | exp | PF | total R | qualified |
|--------|---|-----|-----|---------|-----------|
{rank_rows}

## TEST results (observed once)

| Metric | 1.7.0 H2 | 1.4.0 BASE report |
|--------|----------|-------------------|
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

**OBSERVED:** TP-geometry filtered TEST metrics above; selection used VALIDATION only; 1.4.0
signal generation untouched.

**INFERRED:** {'Exit remap met predeclared success' if success.get('passed') and test_doc['selection_qualified'] else 'H2 TP remapping did not recover a validated edge under predeclared criteria'}.

**UNKNOWN:** Live fills, partial exits / trailing stops, multi-target scaling, prospective data.

## Non-claims

- Does not amend frozen 1.4.0 analysis or DecisionEngine weights.
- Does not combine with failed H1/H3 gates.
- Changing RR alone cannot invent directional edge if hit-rate remains below breakeven for that RR.
"""
    path = ROOT / "docs" / "EXPERIMENT_REPORT_1.7.0.md"
    path.write_text(report, encoding="utf-8")
    print(f"wrote {path}", flush=True)
    print(verdict, flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--select", action="store_true")
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--finalize", action="store_true")
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()
    if not any([args.build, args.select, args.test, args.finalize, args.all]):
        parser.error("specify an action")
    if args.all or args.build:
        run_build()
    if args.all or args.select:
        run_select()
    if args.all or args.test:
        run_test()
    if args.all or args.finalize:
        finalize()


if __name__ == "__main__":
    main()

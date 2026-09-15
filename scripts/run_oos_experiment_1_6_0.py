#!/usr/bin/env python3
"""Pipeline 1.6.0 Arm H3 — direction / alignment emit gating experiment.

Hard rules:
  - Frozen 1.4.0 analysis unchanged.
  - Enrich TRAIN/VAL fit trades (from 1.5.0 corpora) with structure/HTF labels.
  - Select ONLY on VALIDATION; lock before TEST.
  - TEST = locked validation/trades.jsonl filtered by selected gate.

Usage:
  python scripts/run_oos_experiment_1_6_0.py --enrich
  python scripts/run_oos_experiment_1_6_0.py --select
  python scripts/run_oos_experiment_1_6_0.py --test
  python scripts/run_oos_experiment_1_6_0.py --finalize
  python scripts/run_oos_experiment_1_6_0.py --all
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.types.models import NewsContext, Timeframe
from services.backtesting_service.execution import (
    ExecutionConfig,
    SimulatedTrade,
    compute_performance_metrics,
)
from services.quant_engine.pipeline import ANALYSIS_PIPELINE_VERSION, analyze_candle_window
from services.quant_engine.pipeline.calibration_1_6_0 import (
    BASELINE_1_4_0_TEST,
    CANDIDATE_POLICIES,
    DEFAULT_SELECTION,
    DEFAULT_TEST_SUCCESS,
    EXPERIMENT_ARM,
    EXPERIMENT_PIPELINE_VERSION,
    EmitPolicy,
    annotate_alignments,
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
LOOKBACK_BARS = 250
BASE_EXEC = ExecutionConfig("signal_close", "sl_first", 0.0, 0.0, 0.0)

FIT_SOURCE = ROOT / "validation_1_5_0"
OUT_DIR = ROOT / "validation_1_6_0"
BASELINE_VALIDATION = ROOT / "validation"


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


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def enrich_trades(candles, trades: list[dict], label: str) -> list[dict]:
    """Re-run frozen 1.4.0 analysis at each trade timestamp to attach alignment fields."""
    by_ts = {c.timestamp.isoformat(): i for i, c in enumerate(candles)}
    engine = DecisionEngine()
    smc = SMCEngine()
    news = NewsContext(score=10)
    out: list[dict] = []
    t0 = time.perf_counter()
    for n, trade in enumerate(trades, 1):
        ts = trade["timestamp"]
        i = by_ts.get(ts)
        if i is None:
            raise SystemExit(f"timestamp not found in candles: {ts}")
        w0 = max(0, i - LOOKBACK_BARS + 1)
        window = candles[w0 : i + 1]
        bundle = analyze_candle_window(
            "XAUUSD",
            Timeframe.H1,
            window,
            news=news,
            decision_engine=engine,
            smc_engine=smc,
            evaluate=True,
        )
        enriched = dict(trade)
        enriched["structure_external_bias"] = (
            bundle.structure_snapshot.external_bias.value
            if bundle.structure_snapshot
            else None
        )
        enriched["ranking_htf_trend"] = bundle.metadata.get("ranking_htf_trend")
        enriched["ranking_htf_tf"] = bundle.metadata.get("ranking_htf_tf")
        enriched["trend"] = (
            bundle.signal.trend.value if bundle.signal and bundle.signal.trend else None
        )
        enriched["baseline_analysis_version"] = ANALYSIS_PIPELINE_VERSION
        enriched["experiment_pipeline_version"] = EXPERIMENT_PIPELINE_VERSION
        out.append(annotate_alignments(enriched))
        if n % 50 == 0 or n == len(trades):
            print(
                f"  [{label}] {n}/{len(trades)} "
                f"({time.perf_counter() - t0:.1f}s)",
                flush=True,
            )
    return out


def run_enrich() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    actual = _sha256_file(SOURCE_PATH)
    if actual != EXPECTED_SHA256:
        raise SystemExit(f"dataset hash mismatch: {actual}")

    train_src = FIT_SOURCE / "fit_train_trades.jsonl"
    val_src = FIT_SOURCE / "fit_validation_trades.jsonl"
    if not train_src.exists() or not val_src.exists():
        raise SystemExit(
            f"missing 1.5.0 fit corpora under {FIT_SOURCE} — run 1.5.0 --generate-fit first"
        )

    print(f"loading {SOURCE_PATH} ...", flush=True)
    candles = load_candles_csv(SOURCE_PATH, symbol="XAUUSD", timeframe=Timeframe.H1)
    print(f"loaded {len(candles)} candles", flush=True)

    train = load_jsonl(train_src)
    val = load_jsonl(val_src)
    print(f"enriching TRAIN n={len(train)}", flush=True)
    train_e = enrich_trades(candles, train, "train")
    print(f"enriching VALIDATION n={len(val)}", flush=True)
    val_e = enrich_trades(candles, val, "validation")

    write_jsonl(OUT_DIR / "fit_train_trades.jsonl", train_e)
    write_jsonl(OUT_DIR / "fit_validation_trades.jsonl", val_e)
    summary = {
        "train_trades": len(train_e),
        "validation_trades": len(val_e),
        "dataset_sha256": actual,
        "source_fit": str(FIT_SOURCE.relative_to(ROOT)),
        "baseline_analysis_version": ANALYSIS_PIPELINE_VERSION,
        "experiment_version": EXPERIMENT_PIPELINE_VERSION,
        "arm": EXPERIMENT_ARM,
        "enriched_at": datetime.now(timezone.utc).isoformat(),
    }
    (OUT_DIR / "fit_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


def run_select() -> dict:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if (OUT_DIR / "test_metrics.json").exists():
        raise SystemExit("test_metrics.json already exists — selection must precede TEST")

    train_trades = [annotate_alignments(t) for t in load_jsonl(OUT_DIR / "fit_train_trades.jsonl")]
    val_trades = [annotate_alignments(t) for t in load_jsonl(OUT_DIR / "fit_validation_trades.jsonl")]

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
            "Alignment labels match forensics align_bias().",
        ],
    }
    raw = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    payload["selection_sha256"] = _sha256_bytes(raw.encode())
    path = OUT_DIR / "selection.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {path}", flush=True)
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
        raise SystemExit("TEST already evaluated — one shot only")

    selection_doc = json.loads(selection_path.read_text(encoding="utf-8"))
    sel = selection_doc["selection"]
    if not sel.get("selected"):
        raise SystemExit("no selected policy")

    policy = EmitPolicy.from_dict(sel["selected"])
    baseline_trades = [
        annotate_alignments(t) for t in load_jsonl(BASELINE_VALIDATION / "trades.jsonl")
    ]
    filtered = filter_trades(baseline_trades, policy)
    metrics = metrics_from_trade_dicts(filtered)
    success = evaluate_test_success(metrics, criteria=DEFAULT_TEST_SUCCESS, baseline=BASELINE_1_4_0_TEST)

    signals = [
        {
            "signal_id": t["signal_id"],
            "timestamp": t["timestamp"],
            "direction": t["direction"],
            "score": t["score"],
            "confidence": t.get("confidence"),
            "structure_external_bias": t.get("structure_external_bias"),
            "ranking_htf_trend": t.get("ranking_htf_trend"),
            "structure_alignment": t.get("structure_alignment"),
            "htf_alignment": t.get("htf_alignment"),
            "pipeline_version": EXPERIMENT_PIPELINE_VERSION,
            "baseline_analysis_version": ANALYSIS_PIPELINE_VERSION,
            "emit_policy": policy.name,
            "month": t.get("month"),
        }
        for t in filtered
    ]
    write_jsonl(OUT_DIR / "signals.jsonl", signals)
    write_jsonl(OUT_DIR / "trades.jsonl", filtered)

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
        "source_trades": "validation/trades.jsonl",
        "note": (
            "TEST trades are locked 1.4.0 OOS corpus filtered by H3 emit policy; "
            "underlying analysis unchanged."
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
        "lookback_bars": LOOKBACK_BARS,
        "execution": asdict(BASE_EXEC),
        "candidates": [p.to_dict() for p in CANDIDATE_POLICIES],
        "selection_criteria": asdict(DEFAULT_SELECTION),
        "test_success_criteria": asdict(DEFAULT_TEST_SUCCESS),
        "selected_policy": test_doc.get("emit_policy"),
        "parameter_fitting": "discrete_direction_alignment_gate_on_validation_only",
        "fit_source": "validation_1_5_0 fit trades + 1.4.0 re-analysis enrichment",
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
    ranking = sel.get("ranking") or []
    rank_rows = "\n".join(
        f"| {r['name']} | {r.get('total_trades')} | {r.get('expectancy')} | {r.get('profit_factor')} | {r.get('qualified')} |"
        for r in ranking
    )
    verdict = (
        "PASSED EXPERIMENT SUCCESS CRITERIA"
        if success.get("passed") and test_doc["selection_qualified"]
        else "FAILED EXPERIMENT"
    )
    selected_name = (sel.get("selected") or {}).get("name")
    report = f"""# Experiment Report — Pipeline {EXPERIMENT_PIPELINE_VERSION} (Arm {EXPERIMENT_ARM})

**Status:** {verdict}  
**Generated:** {datetime.now(timezone.utc).isoformat()}

## Predeclared design

| Field | Value |
|-------|-------|
| Arm | {EXPERIMENT_ARM} — direction / structure / HTF emit gating |
| Baseline analysis | `{ANALYSIS_PIPELINE_VERSION}` (unchanged) |
| Experiment version | `{EXPERIMENT_PIPELINE_VERSION}` (emit gate only) |
| Dataset | `{DATASET_ID}` |
| Hash | `{actual}` |
| Fit | TRAIN 2022 / VALIDATION 2023 (enriched from 1.5.0 corpora) |
| TEST | 2024-01-01 → 2024-07-11 (once) |

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

| Policy | n | exp | PF | qualified |
|--------|---|-----|-----|-----------|
{rank_rows}

## TEST results (observed once)

| Metric | 1.6.0 H3 | 1.4.0 BASE |
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

**INFERRED:** {'Gate met predeclared success' if success.get('passed') and test_doc['selection_qualified'] else 'H3 direction/alignment gating did not recover a validated edge under predeclared criteria'}.

**UNKNOWN:** Live fills, prospective generalization, whether exit geometry (H2) would fare better.

## Non-claims

- Does not amend or rehabilitate frozen 1.4.0.
- Does not authorize combining with failed H1 score bands into a silent dump.
- Subgroup forensics remain exploratory; this arm tested only the predeclared candidate set.
"""
    report_path = ROOT / "docs" / "EXPERIMENT_REPORT_1.6.0.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"wrote {report_path}", flush=True)
    print(verdict, flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--enrich", action="store_true")
    parser.add_argument("--select", action="store_true")
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--finalize", action="store_true")
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()
    if not any([args.enrich, args.select, args.test, args.finalize, args.all]):
        parser.error("specify an action")
    if args.all or args.enrich:
        run_enrich()
    if args.all or args.select:
        run_select()
    if args.all or args.test:
        run_test()
    if args.all or args.finalize:
        finalize()


if __name__ == "__main__":
    main()

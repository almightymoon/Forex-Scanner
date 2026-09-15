#!/usr/bin/env python3
"""Pipeline 1.8.0 Arm H4 — zone rank / liquidity emit gating.

Enrich TRAIN/VAL fit signals with forensics-compatible zone labels.
TEST joins locked validation/trades.jsonl with forensics_enrichment_cache.json.

Usage:
  python scripts/run_oos_experiment_1_8_0.py --enrich
  python scripts/run_oos_experiment_1_8_0.py --select
  python scripts/run_oos_experiment_1_8_0.py --test
  python scripts/run_oos_experiment_1_8_0.py --finalize
  python scripts/run_oos_experiment_1_8_0.py --all
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
from services.quant_engine.pipeline.calibration_1_8_0 import (
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

SOURCE_PATH = (
    ROOT
    / "benchmarks/data/retrospective/XAUUSD/H1_2022_2024_v1/XAUUSD_H1_2022_2024.real.csv.gz"
)
EXPECTED_SHA256 = "eac96d050a6bacfe879a0506143a053d4ce5ab7304b94cfbab91067211040d73"
LOOKBACK_BARS = 250
BASE_EXEC = ExecutionConfig("signal_close", "sl_first", 0.0, 0.0, 0.0)
FIT_CHUNKS = ROOT / "validation_1_5_0" / "fit_chunks"
BASELINE_VALIDATION = ROOT / "validation"
ENRICH_CACHE_TEST = BASELINE_VALIDATION / "forensics_enrichment_cache.json"
OUT_DIR = ROOT / "validation_1_8_0"
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
    n = m.total_trades
    if n == 0:
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
            score=t.get("score") or 0,
            ambiguous=t.get("ambiguous", False),
            bars_held=t.get("bars_held") or 0,
        )
        for t in trades
    ]


def metrics_from_trade_dicts(trades: list[dict]) -> dict[str, Any]:
    return metrics_dict([]) if not trades else metrics_dict(trades_to_sims(trades))


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def load_fit_pairs(months: list[str]) -> list[dict]:
    """Join chunk signals + trades by signal_id."""
    out: list[dict] = []
    for ym in months:
        payload = json.loads((FIT_CHUNKS / f"{ym}.json").read_text(encoding="utf-8"))
        trades = {t["signal_id"]: t for t in payload.get("trades") or []}
        for sig in payload.get("signals") or []:
            tr = trades.get(sig["signal_id"])
            if not tr:
                continue
            row = dict(tr)
            row["entry"] = sig.get("entry", tr.get("entry_price"))
            row["stop_loss"] = sig.get("stop_loss")
            row["take_profit_1"] = sig.get("take_profit_1")
            out.append(row)
    return out


def enrich_zone_context(candles, rows: list[dict], label: str) -> list[dict]:
    """Forensics-compatible primary_rank + liquidity_relation enrichment."""
    by_ts = {c.timestamp.isoformat(): i for i, c in enumerate(candles)}
    engine = DecisionEngine()
    smc = SMCEngine()
    news = NewsContext(score=10)
    out: list[dict] = []
    t0 = time.perf_counter()
    for k, row in enumerate(rows, 1):
        i = by_ts.get(row["timestamp"])
        if i is None:
            raise SystemExit(f"missing timestamp {row['timestamp']}")
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
        fvg_meta = []
        ob_meta = []
        for p in bundle.smc_patterns:
            ctx = (p.metadata or {}).get("zone_context") or {}
            meta = {
                "zone_id": (p.metadata or {}).get("zone_id"),
                "direction": p.direction.value if p.direction else None,
                "zone_context": ctx,
            }
            if p.pattern_type == "fvg":
                fvg_meta.append(meta)
            elif p.pattern_type == "order_block":
                ob_meta.append(meta)

        d = str(row["direction"]).lower()
        primary = None
        primary_class = "neither"
        for meta in fvg_meta:
            if (meta.get("direction") or "").lower() == d:
                primary = meta
                primary_class = "fvg"
                break
        if primary is None:
            for meta in ob_meta:
                if (meta.get("direction") or "").lower() == d:
                    primary = meta
                    primary_class = "ob"
                    break

        rank = None
        if primary and primary_class == "fvg":
            for idx, meta in enumerate(fvg_meta, start=1):
                if meta.get("zone_id") == primary.get("zone_id"):
                    rank = idx
                    break
        elif primary and primary_class == "ob":
            for idx, meta in enumerate(ob_meta, start=1):
                if meta.get("zone_id") == primary.get("zone_id"):
                    rank = idx
                    break

        ctx = (primary or {}).get("zone_context") or {}
        enriched = dict(row)
        enriched["primary_class"] = primary_class
        enriched["primary_rank"] = rank
        enriched["liquidity_relation"] = ctx.get("liquidity_relation") or "UNKNOWN"
        enriched["distance_atr"] = ctx.get("distance_atr")
        enriched["freshness_bars"] = ctx.get("freshness_bars")
        enriched["baseline_analysis_version"] = ANALYSIS_PIPELINE_VERSION
        enriched["experiment_pipeline_version"] = EXPERIMENT_PIPELINE_VERSION
        out.append(enriched)
        if k % 50 == 0 or k == len(rows):
            print(f"  [{label}] {k}/{len(rows)} ({time.perf_counter()-t0:.1f}s)", flush=True)
    return out


def run_enrich() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    actual = _sha256_file(SOURCE_PATH)
    if actual != EXPECTED_SHA256:
        raise SystemExit(f"hash mismatch {actual}")
    print(f"loading candles...", flush=True)
    candles = load_candles_csv(SOURCE_PATH, symbol="XAUUSD", timeframe=Timeframe.H1)
    train = load_fit_pairs(TRAIN_MONTHS)
    val = load_fit_pairs(VAL_MONTHS)
    print(f"enriching TRAIN n={len(train)}", flush=True)
    train_e = enrich_zone_context(candles, train, "train")
    print(f"enriching VALIDATION n={len(val)}", flush=True)
    val_e = enrich_zone_context(candles, val, "validation")
    write_jsonl(OUT_DIR / "fit_train_trades.jsonl", train_e)
    write_jsonl(OUT_DIR / "fit_validation_trades.jsonl", val_e)
    summary = {
        "train_trades": len(train_e),
        "validation_trades": len(val_e),
        "dataset_sha256": actual,
        "experiment_version": EXPERIMENT_PIPELINE_VERSION,
        "arm": EXPERIMENT_ARM,
        "enriched_at": datetime.now(timezone.utc).isoformat(),
    }
    (OUT_DIR / "fit_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


def run_select() -> dict:
    if (OUT_DIR / "test_metrics.json").exists():
        raise SystemExit("TEST already done")
    train = load_jsonl(OUT_DIR / "fit_train_trades.jsonl")
    val = load_jsonl(OUT_DIR / "fit_validation_trades.jsonl")
    train_m = {p.name: metrics_from_trade_dicts(filter_trades(train, p)) for p in CANDIDATE_POLICIES}
    val_m = {p.name: metrics_from_trade_dicts(filter_trades(val, p)) for p in CANDIDATE_POLICIES}
    selection = select_policy(val_m)
    payload = {
        "locked_at": datetime.now(timezone.utc).isoformat(),
        "experiment_version": EXPERIMENT_PIPELINE_VERSION,
        "arm": EXPERIMENT_ARM,
        "baseline_analysis_version": ANALYSIS_PIPELINE_VERSION,
        "selection_criteria": asdict(DEFAULT_SELECTION),
        "test_success_criteria": asdict(DEFAULT_TEST_SUCCESS),
        "candidates": [p.to_dict() for p in CANDIDATE_POLICIES],
        "train_metrics_by_policy": train_m,
        "validation_metrics_by_policy": val_m,
        "selection": selection,
        "test_not_evaluated_yet": True,
    }
    raw = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    payload["selection_sha256"] = _sha256_bytes(raw.encode())
    (OUT_DIR / "selection.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"qualified={selection['qualified']} selected={selection.get('selected')}", flush=True)
    return payload


def run_test() -> dict:
    if (OUT_DIR / "test_metrics.json").exists():
        raise SystemExit("TEST already evaluated")
    selection_doc = json.loads((OUT_DIR / "selection.json").read_text(encoding="utf-8"))
    policy = EmitPolicy.from_dict(selection_doc["selection"]["selected"])
    cache = json.loads(ENRICH_CACHE_TEST.read_text(encoding="utf-8"))
    baseline = load_jsonl(BASELINE_VALIDATION / "trades.jsonl")
    joined = []
    for t in baseline:
        e = cache.get(t["signal_id"]) or {}
        row = dict(t)
        row["primary_rank"] = e.get("primary_rank")
        row["primary_class"] = e.get("primary_class")
        row["liquidity_relation"] = e.get("liquidity_relation") or "UNKNOWN"
        row["distance_atr"] = e.get("distance_atr")
        row["freshness_bars"] = e.get("freshness_bars")
        joined.append(row)
    filtered = filter_trades(joined, policy)
    metrics = metrics_from_trade_dicts(filtered)
    success = evaluate_test_success(metrics)
    write_jsonl(OUT_DIR / "trades.jsonl", filtered)
    test_doc = {
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "experiment_version": EXPERIMENT_PIPELINE_VERSION,
        "arm": EXPERIMENT_ARM,
        "emit_policy": policy.to_dict(),
        "selection_qualified": bool(selection_doc["selection"].get("qualified")),
        "baseline_test_trades": len(joined),
        "filtered_test_trades": len(filtered),
        "metrics": metrics,
        "success": success,
        "baseline_1_4_0": BASELINE_1_4_0_TEST,
        "enrichment_source": "validation/forensics_enrichment_cache.json",
    }
    (OUT_DIR / "test_metrics.json").write_text(json.dumps(test_doc, indent=2) + "\n", encoding="utf-8")
    selection_doc["test_not_evaluated_yet"] = False
    (OUT_DIR / "selection.json").write_text(json.dumps(selection_doc, indent=2) + "\n", encoding="utf-8")
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
        "dataset_id": "xauusd_h1_oos_v1_retrospective_2022_2024",
        "sha256": actual,
        "experiment_version": EXPERIMENT_PIPELINE_VERSION,
        "arm": EXPERIMENT_ARM,
    }
    config_manifest = {
        "experiment_version": EXPERIMENT_PIPELINE_VERSION,
        "arm": EXPERIMENT_ARM,
        "candidates": [p.to_dict() for p in CANDIDATE_POLICIES],
        "selection_criteria": asdict(DEFAULT_SELECTION),
        "selected_policy": test_doc.get("emit_policy"),
        "mechanism": "emit gate on primary_rank + liquidity_relation",
    }
    config_manifest["config_sha256"] = _sha256_bytes(json.dumps(config_manifest, sort_keys=True).encode())
    for name, obj in [
        ("dataset_manifest.json", dataset_manifest),
        ("config_manifest.json", config_manifest),
        ("metrics.json", {"BASE": m, "success": success, "baseline_1_4_0": BASELINE_1_4_0_TEST}),
        ("walk_forward.json", {
            "train_metrics_by_policy": selection_doc.get("train_metrics_by_policy"),
            "validation_metrics_by_policy": selection_doc.get("validation_metrics_by_policy"),
            "selection": sel,
        }),
        ("reproducibility.json", {
            "dataset_sha256": actual,
            "selection_sha256": selection_doc.get("selection_sha256"),
            "test_enrichment": "validation/forensics_enrichment_cache.json",
        }),
    ]:
        (OUT_DIR / name).write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")

    report = f"""# Experiment Report — Pipeline {EXPERIMENT_PIPELINE_VERSION} (Arm {EXPERIMENT_ARM})

**Status:** {verdict}  
**Generated:** {datetime.now(timezone.utc).isoformat()}

## Predeclared design

| Field | Value |
|-------|-------|
| Arm | {EXPERIMENT_ARM} — zone rank / liquidity emit gating |
| Baseline analysis | `{ANALYSIS_PIPELINE_VERSION}` unchanged |
| Labels | forensics-compatible `primary_rank`, `liquidity_relation` |
| Dataset hash | `{actual}` |

### Selection / TEST criteria

Same floors as H1–H3 (VAL exp≥0, PF≥1, n≥20; TEST exp>0, PF≥1, total R≥−27.434).

## Selection (locked before TEST)

| Field | Value |
|-------|-------|
| Qualified | {sel.get('qualified')} |
| Selected | `{selected_name}` |
| Reason | {sel.get('reason')} |

| Policy | n | exp | PF | total R | qualified |
|--------|---|-----|-----|---------|-----------|
{rank_rows}

## TEST results

| Metric | 1.8.0 H4 | 1.4.0 BASE |
|--------|----------|------------|
| Trades | {m.get('total_trades')} | {BASELINE_1_4_0_TEST['trades']} |
| Win rate | {m.get('win_rate')} | {BASELINE_1_4_0_TEST['win_rate']} |
| Profit factor | {m.get('profit_factor')} | {BASELINE_1_4_0_TEST['profit_factor']} |
| Expectancy | {m.get('expectancy')} | {BASELINE_1_4_0_TEST['expectancy']} |
| Total R | {m.get('total_r')} | {BASELINE_1_4_0_TEST['total_r']} |

```json
{json.dumps(success, indent=2)}
```

## OBSERVED / INFERRED / UNKNOWN

**OBSERVED:** Selection on VALIDATION only; TEST used locked enrichment cache; 1.4.0 untouched.

**INFERRED:** {'H4 met success criteria' if success.get('passed') and test_doc['selection_qualified'] else 'H4 rank/liquidity gates did not recover a validated edge'}.

**UNKNOWN:** Prospective post-2026H1 (H5 accrual incomplete).

## Non-claims

- Does not rehabilitate 1.4.0 or combine with failed H1–H3 arms.
"""
    (ROOT / "docs" / "EXPERIMENT_REPORT_1.8.0.md").write_text(report, encoding="utf-8")
    print(verdict, flush=True)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--enrich", action="store_true")
    p.add_argument("--select", action="store_true")
    p.add_argument("--test", action="store_true")
    p.add_argument("--finalize", action="store_true")
    p.add_argument("--all", action="store_true")
    args = p.parse_args()
    if not any([args.enrich, args.select, args.test, args.finalize, args.all]):
        p.error("specify an action")
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

#!/usr/bin/env python3
"""Post-OOS failure forensics for frozen pipeline 1.4.0.

Diagnosis ONLY. Does not modify analytical behavior, weights, thresholds,
ranking, SL/TP, or the trade set. May re-call analyze_candle_window at locked
signal timestamps to extract zone_context metadata that was not persisted in
validation/signals.jsonl.

Usage:
  python scripts/run_oos_failure_forensics_1_4_0.py
  python scripts/run_oos_failure_forensics_1_4_0.py --skip-enrichment
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.types.models import NewsContext, Timeframe
from services.backtesting_service.execution import pip_size_for_symbol
from services.quant_engine.pipeline import ANALYSIS_PIPELINE_VERSION, analyze_candle_window
from services.quant_engine.decision.engine import DecisionEngine
from services.smc_service.smc import SMCEngine
from swing_engine.benchmark_data import load_candles_csv

OUT_DIR = ROOT / "validation"
REPORT_PATH = ROOT / "docs/OOS_FAILURE_FORENSICS_1.4.0.md"
FORENSICS_JSON = OUT_DIR / "forensics_1_4_0.json"
ENRICH_CACHE = OUT_DIR / "forensics_enrichment_cache.json"
SOURCE_PATH = (
    ROOT
    / "benchmarks/data/retrospective/XAUUSD/H1_2022_2024_v1/XAUUSD_H1_2022_2024.real.csv.gz"
)
LOOKBACK_BARS = 250
FORWARD_BARS = 20
MIN_N_WARN = 30

# Predeclared descriptive bins — NOT optimized against outcomes.
SCORE_BINS = [
    ("low_71_84", 71, 84),
    ("medium_85_94", 85, 94),
    ("high_95_100", 95, 100),
]
CONF_BINS = [
    ("low_lt_0.60", 0.0, 0.599999),
    ("medium_0.60_0.84", 0.60, 0.849999),
    ("high_0.85_1.00", 0.85, 1.000001),
]

REPORT_BASELINE = {
    "trades": 246,
    "win_rate": 38.6,
    "profit_factor": 0.761,
    "expectancy": -0.091,
    "total_r": -22.434,
    "max_drawdown_r": 30.329,
    "consecutive_losses_max": 17,
}


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def align_bias(direction: str, bias: str | None) -> str:
    if not bias or bias in ("undefined", "None"):
        return "UNDEFINED"
    d = direction.lower()
    b = bias.lower()
    if b == "ranging":
        return "NEUTRAL"
    if d == "buy":
        if b == "bullish":
            return "ALIGNED"
        if b == "bearish":
            return "OPPOSED"
    if d == "sell":
        if b == "bearish":
            return "ALIGNED"
        if b == "bullish":
            return "OPPOSED"
    return "UNDEFINED"


def session_utc(ts: str) -> str:
    h = datetime.fromisoformat(ts).astimezone(timezone.utc).hour
    if 0 <= h < 7:
        return "asia_utc"
    if 7 <= h < 12:
        return "london_utc"
    if 12 <= h < 17:
        return "ny_overlap_utc"
    if 17 <= h < 21:
        return "ny_utc"
    return "off_hours_utc"


def planned_geometry(sig: dict) -> dict[str, float]:
    entry = float(sig["entry"])
    sl = float(sig["stop_loss"])
    tp = float(sig["take_profit_1"])
    risk = abs(entry - sl)
    reward = abs(tp - entry)
    rr = reward / risk if risk > 0 else float("nan")
    return {
        "stop_distance": risk,
        "target_distance": reward,
        "planned_rr": rr,
    }


def subgroup_metrics(trades: list[dict]) -> dict[str, Any]:
    n = len(trades)
    if n == 0:
        return {
            "n": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": None,
            "profit_factor": None,
            "expectancy": None,
            "total_r": 0.0,
            "avg_r": None,
            "max_dd_r": None,
            "insufficient": True,
            "warning": "n=0",
        }
    wins = sum(1 for t in trades if t["outcome"] == "win")
    losses = sum(1 for t in trades if t["outcome"] == "loss")
    rs = [float(t["r_multiple"]) for t in trades]
    gp = sum(float(t["pnl_price"]) for t in trades if float(t["pnl_price"]) > 0)
    gl = abs(sum(float(t["pnl_price"]) for t in trades if float(t["pnl_price"]) < 0))
    pf = (gp / gl) if gl > 0 else None
    equity = peak = max_dd = 0.0
    for r in rs:
        equity += r
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    wr = 100.0 * wins / n
    exp = sum(rs) / n
    return {
        "n": n,
        "wins": wins,
        "losses": losses,
        "win_rate": round(wr, 1),
        "profit_factor": round(pf, 3) if pf is not None else None,
        "expectancy": round(exp, 3),
        "total_r": round(sum(rs), 4),
        "avg_r": round(exp, 3),
        "max_dd_r": round(max_dd, 3),
        "insufficient": n < MIN_N_WARN,
        "warning": f"n<{MIN_N_WARN} insufficient subgroup evidence" if n < MIN_N_WARN else None,
    }


def verify_baseline(trades: list[dict], metrics: dict) -> dict[str, Any]:
    sims_r = [float(t["r_multiple"]) for t in trades]
    wins = sum(1 for t in trades if t["outcome"] == "win")
    losses = sum(1 for t in trades if t["outcome"] == "loss")
    n = len(trades)
    wr = round(100.0 * wins / n, 1) if n else 0.0
    gp = sum(float(t["pnl_price"]) for t in trades if float(t["pnl_price"]) > 0)
    gl = abs(sum(float(t["pnl_price"]) for t in trades if float(t["pnl_price"]) < 0))
    pf = round(gp / gl, 3) if gl else None
    total_r = round(sum(sims_r), 4)
    exp = round(sum(sims_r) / n, 3) if n else 0.0
    equity = peak = max_dd = 0.0
    lose = lose_max = 0
    for r in sims_r:
        equity += r
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
        if r < 0:
            lose += 1
            lose_max = max(lose_max, lose)
        else:
            lose = 0
    observed = {
        "trades": n,
        "wins": wins,
        "losses": losses,
        "win_rate": wr,
        "profit_factor": pf,
        "expectancy": exp,
        "total_r": total_r,
        "max_drawdown_r": round(max_dd, 3),
        "consecutive_losses_max": lose_max,
        "metrics_json_baseline": metrics.get("baseline", {}),
    }
    checks = {
        "trades": n == REPORT_BASELINE["trades"],
        "win_rate": wr == REPORT_BASELINE["win_rate"],
        "profit_factor": pf == REPORT_BASELINE["profit_factor"],
        "expectancy": exp == REPORT_BASELINE["expectancy"],
        "total_r": abs(total_r - REPORT_BASELINE["total_r"]) < 0.01,
        "max_drawdown_r": abs(max_dd - REPORT_BASELINE["max_drawdown_r"]) < 0.01,
        "losing_streak": lose_max == REPORT_BASELINE["consecutive_losses_max"],
    }
    observed["match_report"] = all(checks.values())
    observed["check_detail"] = checks
    return observed


def zone_dir_from_id(zid: str | None) -> str | None:
    if not zid:
        return None
    if "-buy-" in zid:
        return "buy"
    if "-sell-" in zid:
        return "sell"
    return None


def best_same_dir_rank(ids: list[str], direction: str) -> int | None:
    for i, zid in enumerate(ids, start=1):
        if zone_dir_from_id(zid) == direction.lower():
            return i
    return None


def enrich_signals(candles, signals: list[dict]) -> dict[str, dict]:
    """Re-analyze at locked signal bars only; extract zone_context (read-only)."""
    by_ts = {c.timestamp.isoformat(): i for i, c in enumerate(candles)}
    engine = DecisionEngine()
    smc = SMCEngine()
    news = NewsContext(score=10)
    out: dict[str, dict] = {}
    t0 = time.perf_counter()
    for k, sig in enumerate(signals, start=1):
        i = by_ts.get(sig["timestamp"])
        if i is None:
            continue
        start = max(0, i + 1 - LOOKBACK_BARS)
        window = candles[start : i + 1]
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
            row = {
                "zone_id": (p.metadata or {}).get("zone_id"),
                "pattern_type": p.pattern_type,
                "direction": p.direction.value if p.direction else None,
                "zone_context": ctx,
                "rank_reasons": (p.metadata or {}).get("rank_reasons"),
            }
            if p.pattern_type == "fvg":
                fvg_meta.append(row)
            elif p.pattern_type == "order_block":
                ob_meta.append(row)

        # Primary zone: first same-direction FVG, else first same-direction OB, else top FVG.
        d = sig["direction"].lower()
        primary = None
        primary_class = "neither"
        for row in fvg_meta:
            if (row.get("direction") or "").lower() == d:
                primary = row
                primary_class = "fvg"
                break
        if primary is None:
            for row in ob_meta:
                if (row.get("direction") or "").lower() == d:
                    primary = row
                    primary_class = "ob"
                    break
        has_fvg_dir = any((r.get("direction") or "").lower() == d for r in fvg_meta)
        has_ob_dir = any((r.get("direction") or "").lower() == d for r in ob_meta)
        if has_fvg_dir and has_ob_dir:
            driver = "fvg_and_ob"
        elif has_fvg_dir:
            driver = "fvg_only"
        elif has_ob_dir:
            driver = "ob_only"
        else:
            driver = "neither"

        ctx = (primary or {}).get("zone_context") or {}
        # Rank position among FVG patterns (1-based) if primary is FVG
        rank = None
        if primary and primary_class == "fvg":
            for idx, row in enumerate(fvg_meta, start=1):
                if row.get("zone_id") == primary.get("zone_id"):
                    rank = idx
                    break
        elif primary and primary_class == "ob":
            for idx, row in enumerate(ob_meta, start=1):
                if row.get("zone_id") == primary.get("zone_id"):
                    rank = idx
                    break

        out[sig["signal_id"]] = {
            "pipeline_version": bundle.pipeline_version,
            "driver_class": driver,
            "primary_class": primary_class,
            "primary_zone_id": (primary or {}).get("zone_id"),
            "primary_rank": rank,
            "lifecycle_state": ctx.get("mitigation_state") or ctx.get("lifecycle_state"),
            "structure_alignment_zone": ctx.get("structure_alignment"),
            "trend_alignment_zone": ctx.get("trend_alignment"),
            "liquidity_relation": ctx.get("liquidity_relation"),
            "distance_atr": ctx.get("distance_atr"),
            "freshness_bars": ctx.get("freshness_bars"),
            "inside_zone": ctx.get("price_inside_zone"),
            "fvg_count": len(fvg_meta),
            "ob_count": len(ob_meta),
        }
        if k % 25 == 0 or k == len(signals):
            print(f"  enrich {k}/{len(signals)} ({time.perf_counter()-t0:.1f}s)", flush=True)
    return out


def mae_mfe_path(
    *,
    direction: str,
    entry: float,
    stop_loss: float,
    take_profit: float,
    forward_bars: list,
) -> dict[str, Any]:
    risk = abs(entry - stop_loss) or 1e-9
    mae = mfe = 0.0
    bars = 0
    hit = None
    for bar in forward_bars:
        bars += 1
        if direction == "buy":
            adverse = max(0.0, entry - bar.low)
            favor = max(0.0, bar.high - entry)
            hit_sl = bar.low <= stop_loss
            hit_tp = bar.high >= take_profit
        else:
            adverse = max(0.0, bar.high - entry)
            favor = max(0.0, entry - bar.low)
            hit_sl = bar.high >= stop_loss
            hit_tp = bar.low <= take_profit
        mae = max(mae, adverse)
        mfe = max(mfe, favor)
        if hit_sl and hit_tp:
            hit = "ambiguous_sl_first"
            break
        if hit_sl:
            hit = "sl"
            break
        if hit_tp:
            hit = "tp"
            break
    else:
        hit = "timeout"

    mae_r = mae / risk
    mfe_r = mfe / risk
    planned_rr = abs(take_profit - entry) / risk

    # Path failure tags (diagnostic labels only)
    tags: list[str] = []
    if bars <= 2 and mae_r >= 0.7 and hit in ("sl", "ambiguous_sl_first"):
        tags.append("immediate_adverse_move")
    if hit in ("sl", "ambiguous_sl_first") and mfe_r < 0.35:
        tags.append("stop_out_before_favorable_excursion")
    if hit in ("sl", "ambiguous_sl_first") and mfe_r >= 0.8 * planned_rr:
        tags.append("target_nearly_reached_then_reversal")
    if hit == "timeout" or (bars >= 12 and mfe_r < 0.4 and mae_r < 0.6):
        tags.append("prolonged_stagnation")
    if planned_rr < 1.0:
        tags.append("poor_planned_rr")
    if not tags and hit in ("sl", "ambiguous_sl_first"):
        tags.append("standard_stop_loss")
    return {
        "mae_r": round(mae_r, 4),
        "mfe_r": round(mfe_r, 4),
        "bars_path": bars,
        "path_exit": hit,
        "path_tags": tags,
        "planned_rr": round(planned_rr, 4),
    }


def mean_or_none(xs: list[float]) -> float | None:
    return round(statistics.mean(xs), 4) if xs else None


def fmt_metrics(m: dict) -> str:
    warn = " ⚠ n<30" if m.get("insufficient") else ""
    pf = m["profit_factor"] if m["profit_factor"] is not None else "n/a"
    wr = m["win_rate"] if m["win_rate"] is not None else "n/a"
    exp = m["expectancy"] if m["expectancy"] is not None else "n/a"
    return (
        f"n={m['n']}{warn} | WR={wr}% | PF={pf} | exp={exp} | "
        f"totalR={m['total_r']} | maxDD={m['max_dd_r']}"
    )


def bucket_score(score: int) -> str:
    for name, lo, hi in SCORE_BINS:
        if lo <= score <= hi:
            return name
    return "out_of_bin"


def bucket_conf(c: float) -> str:
    for name, lo, hi in CONF_BINS:
        if lo <= c <= hi:
            return name
    return "out_of_bin"


def build_report(payload: dict) -> str:
    v = payload["verification"]
    lines: list[str] = []
    a = lines.append
    a("# OOS Failure Forensics — 1.4.0")
    a("")
    a(f"Generated: {payload['generated_at']}")
    a("")
    a("**Scope:** diagnosis only. Pipeline 1.4.0 unchanged. No tuning.")
    a("")
    a(
        "> These subgroup relationships are exploratory and are not validated "
        "predictive rules. Multiple comparisons inflate false discoveries."
    )
    a("")
    a("## 1. Frozen baseline")
    a("")
    a("| Field | Value |")
    a("|-------|-------|")
    a("| Pipeline | 1.4.0 (frozen) |")
    a("| Dataset | `xauusd_h1_oos_v1_retrospective_2022_2024` |")
    a("| Hash | `eac96d050a6bacfe879a0506143a053d4ce5ab7304b94cfbab91067211040d73` |")
    a("| Test window | 2024-01-01 → 2024-07-11 |")
    a("| Lookback / stride | 250 / 4 |")
    a("| Execution | signal_close / sl_first / costs 0 |")
    a("| Parameter fitting | None |")
    a("")
    a("## 2. Result verification")
    a("")
    a(f"**Match report:** `{v['match_report']}`")
    a("")
    a("| Metric | Observed | Report | Match |")
    a("|--------|----------|--------|-------|")
    for key, label in [
        ("trades", "Trades"),
        ("win_rate", "Win rate"),
        ("profit_factor", "PF"),
        ("expectancy", "Expectancy"),
        ("total_r", "Total R"),
        ("max_drawdown_r", "Max DD R"),
        ("consecutive_losses_max", "Losing streak"),
    ]:
        obs = v[key]
        exp = REPORT_BASELINE[key]
        ok = v["check_detail"].get(
            {
                "consecutive_losses_max": "losing_streak",
            }.get(key, key),
            True,
        )
        a(f"| {label} | {obs} | {exp} | {ok} |")
    a("")
    if not v["match_report"]:
        a("**STOP:** numbers inconsistent with locked report. Do not interpret further.")
        a("")
        return "\n".join(lines)

    dist = payload["distributions"]
    a("## 3. Winner vs loser analysis")
    a("")
    a(f"Winners n={dist['n_wins']}, Losers n={dist['n_losses']}.")
    a("")
    a("| Feature | Winners | Losers | Diff (W−L) |")
    a("|---------|---------|--------|------------|")
    for row in payload["winner_loser"]:
        a(
            f"| {row['feature']} | {row['winners']} | {row['losers']} | {row['diff']} |"
        )
    a("")
    a("## 4. Score/confidence calibration")
    a("")
    a("Predeclared bins (not outcome-optimized).")
    a("")
    a("### Score")
    a("")
    a("| Bin | Metrics |")
    a("|-----|---------|")
    for name, m in payload["score_bins"].items():
        a(f"| {name} | {fmt_metrics(m)} |")
    a("")
    a("### Confidence")
    a("")
    a("| Bin | Metrics |")
    a("|-----|---------|")
    for name, m in payload["conf_bins"].items():
        a(f"| {name} | {fmt_metrics(m)} |")
    a("")
    a("## 5. Long vs short")
    a("")
    a("| Side | Metrics |")
    a("|------|---------|")
    for name, m in payload["direction"].items():
        a(f"| {name} | {fmt_metrics(m)} |")
    a("")
    a("## 6. Structure alignment")
    a("")
    a("Signal direction vs `structure_external_bias`.")
    a("")
    a("| Alignment | Metrics |")
    a("|-----------|---------|")
    for name, m in payload["structure_alignment"].items():
        a(f"| {name} | {fmt_metrics(m)} |")
    a("")
    a("## 7. HTF alignment")
    a("")
    a("Signal direction vs `ranking_htf_trend`.")
    a("")
    a("| Alignment | Metrics |")
    a("|-----------|---------|")
    for name, m in payload["htf_alignment"].items():
        a(f"| {name} | {fmt_metrics(m)} |")
    a("")
    a("### Combinations (structure × HTF)")
    a("")
    a("| Combo | Metrics |")
    a("|-------|---------|")
    for name, m in payload["struct_htf_combo"].items():
        a(f"| {name} | {fmt_metrics(m)} |")
    a("")
    a("## 8. Liquidity relation")
    a("")
    if payload.get("enrichment_skipped"):
        a("Enrichment skipped — liquidity_relation **UNKNOWN** at trade level "
          "(not persisted in locked signals.jsonl).")
    else:
        a("From re-analysis zone_context on primary same-direction zone (read-only).")
        a("")
        a("| Relation | Metrics |")
        a("|----------|---------|")
        for name, m in payload["liquidity_relation"].items():
            a(f"| {name} | {fmt_metrics(m)} |")
    a("")
    a("## 9. FVG vs OB")
    a("")
    if payload.get("enrichment_skipped"):
        a("Driver class enrichment skipped. Artifact-only: every signal had both "
          "`fvg` and `order_block` in `smc_pattern_types` (n=246).")
    else:
        a("| Driver | Metrics |")
        a("|--------|---------|")
        for name, m in payload["fvg_ob"].items():
            a(f"| {name} | {fmt_metrics(m)} |")
    a("")
    a("## 10. Zone rank")
    a("")
    if payload.get("enrichment_skipped"):
        a("Primary zone rank enrichment skipped. Artifact proxy: best same-direction "
          "rank in ranked_fvg_ids / ranked_ob_ids:")
        a("")
        a("| Proxy rank | Metrics |")
        a("|------------|---------|")
        for name, m in payload["zone_rank_proxy"].items():
            a(f"| {name} | {fmt_metrics(m)} |")
    else:
        a("Primary same-direction zone rank among soft-capped SMC zone patterns.")
        a("")
        a("| Rank | Metrics |")
        a("|------|---------|")
        for name, m in payload["zone_rank"].items():
            a(f"| {name} | {fmt_metrics(m)} |")
    a("")
    a("## 11. Temporal stability")
    a("")
    a("| Period | Metrics |")
    a("|--------|---------|")
    for name, m in payload["by_month"].items():
        a(f"| {name} | {fmt_metrics(m)} |")
    a("")
    a("| Quarter | Metrics |")
    a("|---------|---------|")
    for name, m in payload["by_quarter"].items():
        a(f"| {name} | {fmt_metrics(m)} |")
    a("")
    a("## 12. Regime analysis")
    a("")
    a("Canonical labels: `structure_external_bias` / signal `trend`.")
    a("")
    a("| Regime (structure) | Metrics |")
    a("|--------------------|---------|")
    for name, m in payload["regime_structure"].items():
        a(f"| {name} | {fmt_metrics(m)} |")
    a("")
    a("| HTF trend | Metrics |")
    a("|-----------|---------|")
    for name, m in payload["regime_htf"].items():
        a(f"| {name} | {fmt_metrics(m)} |")
    a("")
    a("## 13. MAE/MFE")
    a("")
    a("Causal path on post-signal bars only (diagnostic).")
    a("")
    a(f"- Mean MAE (all): {payload['mae_mfe']['mean_mae_r_all']} R")
    a(f"- Mean MFE (all): {payload['mae_mfe']['mean_mfe_r_all']} R")
    a(f"- Mean MAE (losers): {payload['mae_mfe']['mean_mae_r_losers']} R")
    a(f"- Mean MFE (losers): {payload['mae_mfe']['mean_mfe_r_losers']} R")
    a(f"- Mean MAE (winners): {payload['mae_mfe']['mean_mae_r_winners']} R")
    a(f"- Mean MFE (winners): {payload['mae_mfe']['mean_mfe_r_winners']} R")
    a("")
    a("| Path tag (losers) | Count |")
    a("|------------------|-------|")
    for tag, c in payload["mae_mfe"]["loser_tag_counts"].items():
        a(f"| {tag} | {c} |")
    a("")
    a("## 14. Signal vs execution")
    a("")
    cs = payload["cost_sensitivity"]
    a("| Scenario | Total R | Exp | PF |")
    a("|----------|---------|-----|----|")
    a(f"| BASELINE (0 costs) | {cs['baseline']['total_r']} | {cs['baseline']['expectancy']} | {cs['baseline']['profit_factor']} |")
    a(f"| LOW cost | {cs['low']['total_r']} | {cs['low']['expectancy']} | {cs['low']['profit_factor']} |")
    a(f"| HIGH cost | {cs['high']['total_r']} | {cs['high']['expectancy']} | {cs['high']['profit_factor']} |")
    a("")
    a(
        f"**Signal direction / geometry dominate:** baseline total R = {cs['baseline']['total_r']} "
        f"with zero costs. Costs add ~{round(cs['baseline']['total_r'] - cs['high']['total_r'], 2)} R "
        "of further drag (HIGH vs BASE), but the edge is already negative at zero cost."
    )
    a("")
    a(f"- Mean planned R:R: {payload['geometry']['mean_planned_rr']}")
    a(f"- Median planned R:R: {payload['geometry']['median_planned_rr']}")
    a(f"- Share planned R:R < 1.0: {payload['geometry']['share_rr_lt_1']}")
    a(f"- Mean realized R | winners: {payload['geometry']['mean_r_winners']}")
    a(f"- Mean realized R | losers: {payload['geometry']['mean_r_losers']}")
    a("")
    a("## 15. Data integrity considerations")
    a("")
    for note in payload["data_quirks"]:
        a(f"- {note}")
    a("")
    a("## 16. Exploratory findings")
    a("")
    for f in payload["findings"]:
        a(f"- {f}")
    a("")
    a("## 17. Hypotheses for future experiments")
    a("")
    a("**NOT implemented. Separate versioned experiments only.**")
    a("")
    for h in payload["hypotheses"]:
        a(f"### {h['title']}")
        a(f"- **Hypothesis:** {h['hypothesis']}")
        a(f"- **Evidence:** {h['evidence']}")
        a(f"- **Expected mechanism:** {h['mechanism']}")
        a(f"- **Experiment required:** {h['experiment']}")
        a(f"- **Pipeline version impact:** {h['version_impact']}")
        a("")
    a("## 18. What we must NOT conclude")
    a("")
    for x in payload["must_not_conclude"]:
        a(f"- {x}")
    a("")
    a("## 19. Final diagnosis")
    a("")
    a(f"**Categories:** {', '.join(payload['diagnosis_categories'])}")
    a("")
    a(payload["diagnosis_narrative"])
    a("")
    a("---")
    a("")
    a("## Appendix — distributions (descriptive)")
    a("")
    a(f"- Direction: {dist['direction']}")
    a(f"- Session UTC: {dist['session']}")
    a(f"- Month counts: {dist['month']}")
    a(f"- R outcome mean/std: {dist['r_mean']} / {dist['r_std']}")
    a(f"- Holding bars mean: {dist['bars_held_mean']}")
    a(f"- News: {payload['news']}")
    a("")
    a(f"Pipeline confirmation: `{payload['pipeline_version_confirmed']}`")
    a(f"Enrichment used: `{not payload.get('enrichment_skipped')}`")
    a("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-enrichment", action="store_true")
    ap.add_argument(
        "--force-enrichment",
        action="store_true",
        help="Recompute zone_context enrichment even if cache exists",
    )
    args = ap.parse_args()

    if ANALYSIS_PIPELINE_VERSION != "1.4.0":
        print(f"ABORT: pipeline is {ANALYSIS_PIPELINE_VERSION}, expected 1.4.0")
        return 2

    trades = load_jsonl(OUT_DIR / "trades.jsonl")
    signals = load_jsonl(OUT_DIR / "signals.jsonl")
    metrics = json.loads((OUT_DIR / "metrics.json").read_text(encoding="utf-8"))
    sig_by_id = {s["signal_id"]: s for s in signals}

    print("Phase 1 — verify baseline...", flush=True)
    verification = verify_baseline(trades, metrics)
    print(json.dumps(verification["check_detail"], indent=2))
    if not verification["match_report"]:
        print("STOP: inconsistent with locked report")
        REPORT_PATH.write_text(build_report({
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "verification": verification,
            "pipeline_version_confirmed": ANALYSIS_PIPELINE_VERSION,
            "enrichment_skipped": True,
            "distributions": {},
            "winner_loser": [],
            "score_bins": {},
            "conf_bins": {},
            "direction": {},
            "structure_alignment": {},
            "htf_alignment": {},
            "struct_htf_combo": {},
            "liquidity_relation": {},
            "fvg_ob": {},
            "zone_rank": {},
            "zone_rank_proxy": {},
            "by_month": {},
            "by_quarter": {},
            "regime_structure": {},
            "regime_htf": {},
            "mae_mfe": {},
            "cost_sensitivity": {"baseline": {}, "low": {}, "high": {}},
            "geometry": {},
            "data_quirks": [],
            "findings": [],
            "hypotheses": [],
            "must_not_conclude": [],
            "diagnosis_categories": ["INVALID"],
            "diagnosis_narrative": "Verification failed.",
            "news": "UNKNOWN",
        }), encoding="utf-8")
        return 1

    # Join rows
    rows: list[dict] = []
    for t in trades:
        s = sig_by_id[t["signal_id"]]
        geo = planned_geometry(s)
        row = {**t, **{f"sig_{k}": s[k] for k in s if k not in t}}
        row.update(geo)
        row["htf_align"] = align_bias(t["direction"], t.get("ranking_htf_trend"))
        row["struct_align"] = align_bias(t["direction"], t.get("structure_external_bias"))
        row["session"] = session_utc(t["timestamp"])
        row["score_bin"] = bucket_score(int(t["score"]))
        row["conf_bin"] = bucket_conf(float(t["confidence"]))
        row["quarter"] = (
            "2024Q1" if t["month"] in ("2024-01", "2024-02", "2024-03")
            else "2024Q2" if t["month"] in ("2024-04", "2024-05", "2024-06")
            else "2024Q3"
        )
        # Artifact proxy ranks
        row["fvg_rank_proxy"] = best_same_dir_rank(s.get("ranked_fvg_ids") or [], t["direction"])
        row["ob_rank_proxy"] = best_same_dir_rank(s.get("ranked_ob_ids") or [], t["direction"])
        row["zone_rank_proxy"] = row["fvg_rank_proxy"] or row["ob_rank_proxy"]
        rows.append(row)

    print("Loading candles for MAE/MFE...", flush=True)
    candles = load_candles_csv(
        SOURCE_PATH,
        symbol="XAUUSD",
        timeframe=Timeframe.H1,
        expected_sha256="eac96d050a6bacfe879a0506143a053d4ce5ab7304b94cfbab91067211040d73",
    )
    by_ts = {c.timestamp.isoformat(): i for i, c in enumerate(candles)}
    pip = pip_size_for_symbol("XAUUSD")

    for row in rows:
        s = sig_by_id[row["signal_id"]]
        i = by_ts[s["timestamp"]]
        path = mae_mfe_path(
            direction=s["direction"],
            entry=float(s["entry"]),
            stop_loss=float(s["stop_loss"]),
            take_profit=float(s["take_profit_1"]),
            forward_bars=candles[i + 1 : i + 1 + FORWARD_BARS],
        )
        row.update(path)

    enrichment: dict[str, dict] = {}
    enrichment_skipped = bool(args.skip_enrichment)
    if not enrichment_skipped:
        if ENRICH_CACHE.exists() and not args.force_enrichment:
            print(f"Loading enrichment cache {ENRICH_CACHE}...", flush=True)
            enrichment = json.loads(ENRICH_CACHE.read_text(encoding="utf-8"))
        else:
            print("Enriching zone_context via frozen analyze_candle_window...", flush=True)
            enrichment = enrich_signals(candles, signals)
            ENRICH_CACHE.write_text(json.dumps(enrichment, indent=2) + "\n", encoding="utf-8")
            print(f"Wrote enrichment cache {ENRICH_CACHE}", flush=True)
        for row in rows:
            e = enrichment.get(row["signal_id"], {})
            row["driver_class"] = e.get("driver_class", "unknown")
            row["primary_rank"] = e.get("primary_rank")
            row["liquidity_relation"] = e.get("liquidity_relation") or "UNKNOWN"
            row["lifecycle_state"] = e.get("lifecycle_state")
            row["distance_atr"] = e.get("distance_atr")
            row["freshness_bars"] = e.get("freshness_bars")
            row["trend_alignment_zone"] = e.get("trend_alignment_zone")
            row["structure_alignment_zone"] = e.get("structure_alignment_zone")
            if e.get("pipeline_version") and e["pipeline_version"] != "1.4.0":
                print("ABORT: enrichment saw non-1.4.0 pipeline")
                return 2
    else:
        for row in rows:
            row["driver_class"] = "unknown"
            row["liquidity_relation"] = "UNKNOWN"

    winners = [r for r in rows if r["outcome"] == "win"]
    losers = [r for r in rows if r["outcome"] == "loss"]

    def avg(field: str, xs: list[dict]) -> float | None:
        vals = [float(x[field]) for x in xs if x.get(field) is not None and not (
            isinstance(x[field], float) and math.isnan(x[field])
        )]
        return mean_or_none(vals)

    def rate(pred, xs: list[dict]) -> float | None:
        if not xs:
            return None
        return round(100.0 * sum(1 for x in xs if pred(x)) / len(xs), 1)

    winner_loser = [
        {
            "feature": "mean score",
            "winners": avg("score", winners),
            "losers": avg("score", losers),
            "diff": None if avg("score", winners) is None else round(
                avg("score", winners) - avg("score", losers), 3  # type: ignore
            ),
        },
        {
            "feature": "mean confidence",
            "winners": avg("confidence", winners),
            "losers": avg("confidence", losers),
            "diff": round(avg("confidence", winners) - avg("confidence", losers), 4),  # type: ignore
        },
        {
            "feature": "mean planned R:R",
            "winners": avg("planned_rr", winners),
            "losers": avg("planned_rr", losers),
            "diff": round(avg("planned_rr", winners) - avg("planned_rr", losers), 4),  # type: ignore
        },
        {
            "feature": "mean stop distance",
            "winners": avg("stop_distance", winners),
            "losers": avg("stop_distance", losers),
            "diff": round(avg("stop_distance", winners) - avg("stop_distance", losers), 4),  # type: ignore
        },
        {
            "feature": "mean bars held",
            "winners": avg("bars_held", winners),
            "losers": avg("bars_held", losers),
            "diff": round(avg("bars_held", winners) - avg("bars_held", losers), 3),  # type: ignore
        },
        {
            "feature": "mean MAE R",
            "winners": avg("mae_r", winners),
            "losers": avg("mae_r", losers),
            "diff": round(avg("mae_r", winners) - avg("mae_r", losers), 4),  # type: ignore
        },
        {
            "feature": "mean MFE R",
            "winners": avg("mfe_r", winners),
            "losers": avg("mfe_r", losers),
            "diff": round(avg("mfe_r", winners) - avg("mfe_r", losers), 4),  # type: ignore
        },
        {
            "feature": "% HTF ALIGNED",
            "winners": rate(lambda x: x["htf_align"] == "ALIGNED", winners),
            "losers": rate(lambda x: x["htf_align"] == "ALIGNED", losers),
            "diff": round(
                rate(lambda x: x["htf_align"] == "ALIGNED", winners)
                - rate(lambda x: x["htf_align"] == "ALIGNED", losers),
                1,
            ),
        },
        {
            "feature": "% structure ALIGNED",
            "winners": rate(lambda x: x["struct_align"] == "ALIGNED", winners),
            "losers": rate(lambda x: x["struct_align"] == "ALIGNED", losers),
            "diff": round(
                rate(lambda x: x["struct_align"] == "ALIGNED", winners)
                - rate(lambda x: x["struct_align"] == "ALIGNED", losers),
                1,
            ),
        },
        {
            "feature": "% buy",
            "winners": rate(lambda x: x["direction"] == "buy", winners),
            "losers": rate(lambda x: x["direction"] == "buy", losers),
            "diff": round(
                rate(lambda x: x["direction"] == "buy", winners)
                - rate(lambda x: x["direction"] == "buy", losers),
                1,
            ),
        },
    ]
    if not enrichment_skipped:
        winner_loser.extend([
            {
                "feature": "mean primary zone rank",
                "winners": avg("primary_rank", winners),
                "losers": avg("primary_rank", losers),
                "diff": (
                    None if avg("primary_rank", winners) is None or avg("primary_rank", losers) is None
                    else round(avg("primary_rank", winners) - avg("primary_rank", losers), 3)  # type: ignore
                ),
            },
            {
                "feature": "mean distance_atr",
                "winners": avg("distance_atr", winners),
                "losers": avg("distance_atr", losers),
                "diff": (
                    None if avg("distance_atr", winners) is None or avg("distance_atr", losers) is None
                    else round(avg("distance_atr", winners) - avg("distance_atr", losers), 4)  # type: ignore
                ),
            },
            {
                "feature": "mean freshness_bars",
                "winners": avg("freshness_bars", winners),
                "losers": avg("freshness_bars", losers),
                "diff": (
                    None if avg("freshness_bars", winners) is None or avg("freshness_bars", losers) is None
                    else round(avg("freshness_bars", winners) - avg("freshness_bars", losers), 3)  # type: ignore
                ),
            },
        ])

    def group(key_fn) -> dict[str, dict]:
        buckets: dict[str, list] = defaultdict(list)
        for r in rows:
            buckets[str(key_fn(r))].append(r)
        return {k: subgroup_metrics(v) for k, v in sorted(buckets.items(), key=lambda x: x[0])}

    score_bins = group(lambda r: r["score_bin"])
    conf_bins = group(lambda r: r["conf_bin"])
    direction = group(lambda r: r["direction"])
    structure_alignment = group(lambda r: r["struct_align"])
    htf_alignment = group(lambda r: r["htf_align"])
    struct_htf_combo = group(lambda r: f"S:{r['struct_align']}|H:{r['htf_align']}")
    by_month = group(lambda r: r["month"])
    by_quarter = group(lambda r: r["quarter"])
    regime_structure = group(lambda r: r.get("structure_external_bias") or "undefined")
    regime_htf = group(lambda r: r.get("ranking_htf_trend") or "undefined")
    liquidity_relation = group(lambda r: r.get("liquidity_relation") or "UNKNOWN")
    fvg_ob = group(lambda r: r.get("driver_class") or "unknown")
    zone_rank = group(lambda r: str(r.get("primary_rank") or "none"))
    zone_rank_proxy = group(lambda r: str(r.get("zone_rank_proxy") or "none"))

    loser_tags: dict[str, int] = defaultdict(int)
    for r in losers:
        for tag in r.get("path_tags") or []:
            loser_tags[tag] += 1
        if r["htf_align"] == "OPPOSED":
            loser_tags["wrong_directional_bias_htf"] += 1

    mae_mfe = {
        "mean_mae_r_all": avg("mae_r", rows),
        "mean_mfe_r_all": avg("mfe_r", rows),
        "mean_mae_r_losers": avg("mae_r", losers),
        "mean_mfe_r_losers": avg("mfe_r", losers),
        "mean_mae_r_winners": avg("mae_r", winners),
        "mean_mfe_r_winners": avg("mfe_r", winners),
        "loser_tag_counts": dict(sorted(loser_tags.items(), key=lambda x: -x[1])),
    }

    # Cost sensitivity from locked metrics.json
    cs = metrics.get("cost_sensitivity", {})
    cost_sensitivity = {
        "baseline": cs.get("baseline", metrics.get("baseline", {})),
        "low": cs.get("low_cost", {}),
        "high": cs.get("high_cost", {}),
    }

    planned = [r["planned_rr"] for r in rows if not math.isnan(r["planned_rr"])]
    geometry = {
        "mean_planned_rr": mean_or_none(planned),
        "median_planned_rr": round(statistics.median(planned), 4) if planned else None,
        "share_rr_lt_1": round(100.0 * sum(1 for x in planned if x < 1.0) / len(planned), 1) if planned else None,
        "mean_r_winners": avg("r_multiple", winners),
        "mean_r_losers": avg("r_multiple", losers),
    }

    session_metrics = group(lambda r: r["session"])
    rs = [float(r["r_multiple"]) for r in rows]
    distributions = {
        "n_wins": len(winners),
        "n_losses": len(losers),
        "direction": {k: v["n"] for k, v in direction.items()},
        "session": {k: v["n"] for k, v in session_metrics.items()},
        "month": {k: v["n"] for k, v in by_month.items()},
        "r_mean": mean_or_none(rs),
        "r_std": round(statistics.pstdev(rs), 4) if len(rs) > 1 else 0.0,
        "bars_held_mean": avg("bars_held", rows),
    }

    # Findings (exploratory)
    findings = []
    findings.append(
        f"Baseline negative expectancy at zero costs (total R={verification['total_r']}) "
        "— analytical/signal failure, not cost failure."
    )
    buy_m, sell_m = direction.get("buy"), direction.get("sell")
    if buy_m and sell_m:
        findings.append(
            f"Long/short: buy n={buy_m['n']} exp={buy_m['expectancy']}; "
            f"sell n={sell_m['n']} exp={sell_m['expectancy']}."
        )
    # Score calibration monotonicity check (exploratory)
    sb = [(k, score_bins[k]) for k in score_bins]
    findings.append(
        "Score bins (exploratory): "
        + "; ".join(f"{k} exp={m['expectancy']} n={m['n']}" for k, m in sb)
    )
    cb = [(k, conf_bins[k]) for k in conf_bins]
    findings.append(
        "Confidence bins (exploratory): "
        + "; ".join(f"{k} exp={m['expectancy']} n={m['n']}" for k, m in cb)
    )
    findings.append(
        f"Loser path tags dominated by: {list(loser_tags.items())[:5]}"
    )
    findings.append(
        f"Temporal: worst month by total R is "
        f"{min(by_month.items(), key=lambda kv: kv[1]['total_r'])[0]} "
        f"({min(by_month.items(), key=lambda kv: kv[1]['total_r'])[1]})"
    )
    if not enrichment_skipped:
        findings.append(
            "Liquidity / FVG-OB / zone-rank tables use read-only enrichment; "
            "see sections 8–10."
        )
    else:
        findings.append("Enrichment skipped — sections 8–10 partially UNKNOWN / proxy-only.")

    # Diagnosis categories
    cats = ["A. Directional signal weakness"]
    if geometry["mean_planned_rr"] is not None and geometry["mean_planned_rr"] < 1.5:
        # Still check if RR is the main issue
        pass
    # Check if high score worse or similar
    high = score_bins.get("high_95_100")
    low = score_bins.get("low_71_84")
    if high and low and high["n"] >= 30 and low["n"] >= 20:
        if high["expectancy"] is not None and low["expectancy"] is not None:
            if high["expectancy"] <= low["expectancy"] + 0.05:
                cats.append("E. Confidence/score is poorly calibrated")
    # Ranking
    if not enrichment_skipped:
        r1 = zone_rank.get("1")
        if r1 and r1["n"] >= 30 and r1["expectancy"] is not None and r1["expectancy"] < 0:
            cats.append("D. Ranking/context has little predictive value")
    # Regime
    for name, m in regime_structure.items():
        if m["n"] >= 30 and m["expectancy"] is not None and m["expectancy"] < -0.05:
            cats.append("C. Regime dependence")
            break
    if buy_m and sell_m and abs((buy_m["expectancy"] or 0) - (sell_m["expectancy"] or 0)) >= 0.08:
        cats.append("F. Long/short asymmetry")
    # Execution not primary
    # Geometry
    if geometry.get("share_rr_lt_1") and geometry["share_rr_lt_1"] >= 20:
        cats.append("B. Poor reward/risk geometry")
    cats.append("I. Insufficient evidence")  # always true for claiming live edge
    # Deduplicate preserving order
    seen = set()
    cats_u = []
    for c in cats:
        if c not in seen:
            seen.add(c)
            cats_u.append(c)

    diagnosis_narrative = (
        "Frozen 1.4.0 produces a reproducible negative-expectancy trade stream on the "
        "locked 2024 OOS holdout under zero-cost realistic execution rules. Losses are "
        "not explained by spread/slippage (already negative at BASE). Path analysis shows "
        "many stops with limited favorable excursion, consistent with directional/setup "
        "weakness and/or SL/TP geometry that does not compensate for win rate below ~45%. "
        "Score and confidence do not demonstrate clear positive calibration in predeclared "
        "bins. Temporal losses concentrate in mid-2024 (especially June) but are not "
        "confined to a single month. Subgroup contrasts are exploratory only."
    )

    hypotheses = [
        {
            "title": "H1 — Score/confidence thresholding experiment",
            "hypothesis": "Higher score/confidence bins may not improve realized R; a recalibrated mapping or hard filter might change trade mix.",
            "evidence": "See score/confidence bin tables (exploratory).",
            "mechanism": "Remove low-information high-score saturation or require calibrated confidence.",
            "experiment": "Versioned DecisionEngine / confidence mapping A/B on TRAIN only; lock before TEST.",
            "version_impact": "Would require new ANALYSIS_PIPELINE_VERSION if analytical scoring changes.",
        },
        {
            "title": "H2 — SL/TP geometry experiment",
            "hypothesis": "Planned R:R and stop distance may not compensate for ~39% win rate.",
            "evidence": f"Mean planned RR={geometry['mean_planned_rr']}; WR≈38.6%; mean loser R={geometry['mean_r_losers']}.",
            "mechanism": "Wider targets or structure-aware stops change payoff distribution.",
            "experiment": "Separately versioned exit model; do not retune on OOS.",
            "version_impact": "New pipeline version if signal SL/TP construction changes.",
        },
        {
            "title": "H3 — Regime / HTF gating experiment",
            "hypothesis": "Certain structure×HTF combinations may be systematically worse.",
            "evidence": "See structure×HTF combo table; regime tables.",
            "mechanism": "Gate or down-weight opposed setups.",
            "experiment": "Predeclare gates on TRAIN; evaluate once on locked TEST.",
            "version_impact": "New version if DecisionEngine gating changes.",
        },
        {
            "title": "H4 — Zone ranking predictive validity experiment",
            "hypothesis": "Soft-capped zone rank may not correlate with realized R.",
            "evidence": "Zone rank section (enrichment or proxy).",
            "mechanism": "Alternative ranking lexicographic keys or disable soft-cap effects.",
            "experiment": "Versioned ranking module comparison.",
            "version_impact": "New version if ranking rules change.",
        },
        {
            "title": "H5 — Prospective dataset validation",
            "hypothesis": "Retrospective OHLC + stride/lookback evaluation design may differ from live accrual.",
            "evidence": "Known evaluation quirks; FAILED OOS still holds under documented design.",
            "mechanism": "Prospective post-lock data reduces some dataset biases (not a strategy fix).",
            "experiment": "Shadow/paper on prospective candles with identical 1.4.0.",
            "version_impact": "None if 1.4.0 remains frozen.",
        },
    ]

    must_not_conclude = [
        "That any subgroup filter would improve live performance (not tested).",
        "That June 2024 alone 'explains' failure (other months also weak/mixed).",
        "That costs caused the failure (BASE already negative).",
        "That the strategy is profitable under different undocumented assumptions.",
        "That n=246 proves statistical significance of any subgroup contrast.",
        "That changing stride/lookback would salvage 1.4.0 without a new experiment.",
    ]

    data_quirks = [
        "Retrospective OHLC package — not prospective post-2026 certification dataset.",
        "Weekday/session gaps noted in OOS integrity; not repaired.",
        "Evaluation lookback=250 and stride=4 fixed a priori — reduces density vs every-bar expanding window; does not reverse the negative BASE result by itself.",
        "XAU pip_size=0.01 inflates max_drawdown_pips presentation; PnL R multiples use price risk and remain the primary metric.",
        "BASE spread/slippage/commission = 0 — research baseline; HIGH cost worsens results further.",
        "Broker timezone uniqueness UNKNOWN; timestamps treated as UTC-aware from source.",
        "NewsContext was neutral in OOS — news contribution UNKNOWN.",
        "These quirks do not invalidate the FAILED OOS conclusion under the documented protocol; they limit external generalization.",
    ]

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pipeline_version_confirmed": ANALYSIS_PIPELINE_VERSION,
        "verification": verification,
        "enrichment_skipped": enrichment_skipped,
        "distributions": distributions,
        "winner_loser": winner_loser,
        "score_bins": score_bins,
        "conf_bins": conf_bins,
        "direction": direction,
        "structure_alignment": structure_alignment,
        "htf_alignment": htf_alignment,
        "struct_htf_combo": struct_htf_combo,
        "liquidity_relation": liquidity_relation,
        "fvg_ob": fvg_ob,
        "zone_rank": zone_rank,
        "zone_rank_proxy": zone_rank_proxy,
        "by_month": by_month,
        "by_quarter": by_quarter,
        "regime_structure": regime_structure,
        "regime_htf": regime_htf,
        "mae_mfe": mae_mfe,
        "cost_sensitivity": {
            "baseline": {
                "total_r": cost_sensitivity["baseline"].get("total_r"),
                "expectancy": cost_sensitivity["baseline"].get("expectancy"),
                "profit_factor": cost_sensitivity["baseline"].get("profit_factor"),
            },
            "low": {
                "total_r": cost_sensitivity["low"].get("total_r"),
                "expectancy": cost_sensitivity["low"].get("expectancy"),
                "profit_factor": cost_sensitivity["low"].get("profit_factor"),
            },
            "high": {
                "total_r": cost_sensitivity["high"].get("total_r"),
                "expectancy": cost_sensitivity["high"].get("expectancy"),
                "profit_factor": cost_sensitivity["high"].get("profit_factor"),
            },
        },
        "geometry": geometry,
        "data_quirks": data_quirks,
        "findings": findings,
        "hypotheses": hypotheses,
        "must_not_conclude": must_not_conclude,
        "diagnosis_categories": cats_u,
        "diagnosis_narrative": diagnosis_narrative,
        "news": "UNKNOWN — OOS used neutral NewsContext; no causal news metadata on trades.",
        "session_metrics": session_metrics,
    }

    # Refine diagnosis narrative with concrete numbers after computing tables
    buy_exp = direction.get("buy", {}).get("expectancy")
    sell_exp = direction.get("sell", {}).get("expectancy")
    high_exp = score_bins.get("high_95_100", {}).get("expectancy")
    med_exp = score_bins.get("medium_85_94", {}).get("expectancy")
    low_exp = score_bins.get("low_71_84", {}).get("expectancy")
    jun = by_month.get("2024-06", {})
    payload["diagnosis_narrative"] = (
        f"OBSERVED: 246 OOS trades, WR 38.6%, PF 0.761, expectancy −0.091 R, "
        f"total R −22.43, max DD 30.33 R. Zero-cost BASE already negative; "
        f"HIGH cost total R {cost_sensitivity['high'].get('total_r')} (worse). "
        f"Long exp={buy_exp}, short exp={sell_exp}. "
        f"Score bins low/med/high exp={low_exp}/{med_exp}/{high_exp}. "
        f"Worst month 2024-06 total R={jun.get('total_r')} (n={jun.get('n')}). "
        f"Loser paths frequently show stop-out with limited MFE "
        f"(mean loser MFE={mae_mfe['mean_mfe_r_losers']} R vs MAE={mae_mfe['mean_mae_r_losers']} R). "
        "INFERRED: primary failure is directional/setup expectancy under frozen SL/TP geometry, "
        "not execution friction. UNKNOWN: live fills, causal news, prospective generalization. "
        "Subgroup relationships remain exploratory (multiple comparisons)."
    )

    FORENSICS_JSON.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    REPORT_PATH.write_text(build_report(payload), encoding="utf-8")
    print(f"Wrote {FORENSICS_JSON}")
    print(f"Wrote {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

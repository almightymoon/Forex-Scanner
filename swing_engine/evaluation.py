"""Benchmark evaluation with JSON/CSV/Markdown export and version comparison."""

from __future__ import annotations

import csv
import json
import logging
import subprocess
from pathlib import Path
from typing import Any

from swing_engine.config import SwingEngineConfig, get_config
from swing_engine.models import BenchmarkLabel, DetectedSwing, EvaluationReport, SwingScope, SwingTier
from swing_engine.utils import log_stage, pip_size_for_symbol, pips_to_price

logger = logging.getLogger("fxnav.swing_engine.evaluation")


class SwingBenchmarkEvaluator:
    def __init__(self, config: SwingEngineConfig | None = None):
        self._config = config or get_config()

    def evaluate(
        self,
        predicted: list[DetectedSwing],
        ground_truth: list[BenchmarkLabel],
        symbol: str,
        *,
        engine_version: str | None = None,
        benchmark_version: str | None = None,
        regime: str | None = None,
        runtime_ms: float | None = None,
    ) -> EvaluationReport:
        ec = self._config.evaluation
        price_tol = pips_to_price(ec.price_match_tolerance_pips, symbol, self._config)
        index_tol = ec.index_match_tolerance_bars
        pip = pip_size_for_symbol(symbol, self._config)
        confirmed = [s for s in predicted if s.confirmed]

        matched_gt: set[int] = set()
        matched_pred: set[int] = set()
        pairs, delays, price_errors, time_errors = [], [], [], []

        for pi, pred in enumerate(confirmed):
            best_gi, best_score = None, float("inf")
            for gi, label in enumerate(ground_truth):
                if gi in matched_gt or pred.direction.value != label.direction.value:
                    continue
                idx_diff = abs(pred.pivot_index - label.pivot_index)
                if idx_diff <= index_tol and abs(pred.price - label.price) <= price_tol:
                    score = idx_diff + abs(pred.price - label.price) / max(pip, 1e-12)
                    if score < best_score:
                        best_score, best_gi = score, gi
            if best_gi is not None:
                label = ground_truth[best_gi]
                matched_gt.add(best_gi)
                matched_pred.add(pi)
                delays.append(pred.confirmation_delay)
                price_errors.append(abs(pred.price - label.price) / pip)
                time_errors.append(abs(pred.pivot_index - label.pivot_index))
                pairs.append({
                    "predicted_index": pred.pivot_index, "ground_truth_index": label.pivot_index,
                    "delay_bars": pred.confirmation_delay,
                    "price_error_pips": round(abs(pred.price - label.price) / pip, 2),
                    "tier_match": pred.tier == label.tier, "scope_match": pred.scope == label.scope,
                })

        tp = len(matched_pred)
        fp, fn = len(confirmed) - tp, len(ground_truth) - len(matched_gt)
        p = tp / (tp + fp) if (tp + fp) else 0.0
        r = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * p * r / (p + r) if (p + r) else 0.0

        mtp, mfp, mfn = self._subset_metrics(confirmed, ground_truth, matched_pred, matched_gt, "tier", SwingTier.MAJOR)
        etp, efp, efn = self._subset_metrics(confirmed, ground_truth, matched_pred, matched_gt, "scope", SwingScope.EXTERNAL)

        avg_conf = sum(s.confidence for s in confirmed) / len(confirmed) if confirmed else 0.0
        avg_str = sum(s.strength for s in confirmed) / len(confirmed) if confirmed else 0.0
        repaint = self._repainting_rate(confirmed)

        report = EvaluationReport(
            precision=p, recall=r, f1_score=f1, false_positives=fp, false_negatives=fn, true_positives=tp,
            average_detection_delay_bars=sum(delays) / len(delays) if delays else 0.0,
            average_price_error_pips=sum(price_errors) / len(price_errors) if price_errors else 0.0,
            average_time_error_bars=sum(time_errors) / len(time_errors) if time_errors else 0.0,
            major_precision=mtp / (mtp + mfp) if (mtp + mfp) else 0.0,
            major_recall=mtp / (mtp + mfn) if (mtp + mfn) else 0.0,
            external_precision=etp / (etp + efp) if (etp + efp) else 0.0,
            external_recall=etp / (etp + efn) if (etp + efn) else 0.0,
            average_confidence=avg_conf,
            average_strength=avg_str,
            repainting_rate=repaint,
            matched_pairs=pairs,
            metadata={
                "symbol": symbol,
                "predicted": len(confirmed),
                "ground_truth": len(ground_truth),
                "engine_version": engine_version,
                "benchmark_version": benchmark_version,
                "regime": regime,
                "runtime_ms": runtime_ms,
                "commit_hash": _git_commit_hash(),
                "config_snapshot": {
                    "pivot_lookback": self._config.pivot.left_lookback,
                    "confirmation_delay": self._config.confirmation.delay_bars,
                },
            },
        )
        log_stage("evaluation", len(confirmed), tp, f1=round(f1, 4))
        return report

    def _subset_metrics(self, predicted, ground_truth, matched_pred, matched_gt, attr, value):
        tp = sum(1 for i in matched_pred if getattr(predicted[i], attr) == value)
        fp = sum(1 for s in predicted if s.confirmed and getattr(s, attr) == value) - tp
        fn = sum(1 for i, g in enumerate(ground_truth) if getattr(g, attr) == value and i not in matched_gt)
        return tp, fp, fn

    def _repainting_rate(self, swings: list[DetectedSwing]) -> float:
        if not swings:
            return 0.0
        unconfirmed = sum(1 for s in swings if not s.confirmed)
        return unconfirmed / len(swings)


def write_json_report(report: EvaluationReport, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    return path


def write_csv_report(report: EvaluationReport, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["metric", "value"])
        for k, v in report.to_dict().items():
            if k not in ("matched_pairs", "metadata"):
                w.writerow([k, v])
    return path


def write_markdown_report(report: EvaluationReport, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    md = _markdown_summary(report)
    path.write_text(md, encoding="utf-8")
    return path


def write_comparison_charts(reports: dict[str, EvaluationReport], path: Path) -> Path:
    """Write HTML bar charts comparing versions."""
    path.parent.mkdir(parents=True, exist_ok=True)
    versions = list(reports.keys())
    metrics = ["precision", "recall", "f1_score", "major_precision", "external_precision"]
    charts = {m: [getattr(reports[v], m) for v in versions] for m in metrics}
    html = _comparison_chart_html(versions, charts)
    path.write_text(html, encoding="utf-8")
    return path


def _markdown_summary(report: EvaluationReport) -> str:
    meta = report.metadata
    lines = [
        "# Swing Detection Benchmark Report",
        "",
        f"- **Symbol:** {meta.get('symbol', 'N/A')}",
        f"- **Engine version:** {meta.get('engine_version', 'N/A')}",
        f"- **Benchmark version:** {meta.get('benchmark_version', 'N/A')}",
        f"- **Regime:** {meta.get('regime', 'N/A')}",
        f"- **Commit:** {meta.get('commit_hash', 'N/A')}",
        "",
        "## Core Metrics",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Precision | {report.precision:.4f} |",
        f"| Recall | {report.recall:.4f} |",
        f"| F1 | {report.f1_score:.4f} |",
        f"| False Positives | {report.false_positives} |",
        f"| False Negatives | {report.false_negatives} |",
        f"| Detection Delay (bars) | {report.average_detection_delay_bars:.2f} |",
        f"| Price Error (pips) | {report.average_price_error_pips:.2f} |",
        f"| Time Error (bars) | {report.average_time_error_bars:.2f} |",
        "",
        "## Classification",
        f"| Metric | Value |",
        f"| Major Precision | {report.major_precision:.4f} |",
        f"| Major Recall | {report.major_recall:.4f} |",
        f"| External Precision | {report.external_precision:.4f} |",
        f"| External Recall | {report.external_recall:.4f} |",
        f"| Avg Confidence | {report.average_confidence:.4f} |",
        f"| Avg Strength | {report.average_strength:.2f} |",
        f"| Repainting Rate | {report.repainting_rate:.4f} |",
    ]
    return "\n".join(lines) + "\n"


def _comparison_chart_html(versions: list[str], charts: dict[str, list[float]]) -> str:
    bars_js = json.dumps(charts)
    versions_js = json.dumps(versions)
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>Swing Engine Version Comparison</title>
<style>body{{font-family:system-ui;background:#0f172a;color:#e2e8f0;padding:20px}}
.chart{{margin:24px 0}}h2{{font-size:14px;color:#94a3b8}}</style></head><body>
<h1>Version Comparison</h1>
<div id="charts"></div>
<script>
const VERSIONS={versions_js};
const DATA={bars_js};
const colors=['#22c55e','#3b82f6','#f59e0b','#ef4444'];
const root=document.getElementById('charts');
for(const [metric,values] of Object.entries(DATA)){{
  const max=Math.max(...values,0.01);
  const div=document.createElement('div');div.className='chart';
  div.innerHTML='<h2>'+metric+'</h2>';
  values.forEach((v,i)=>{{
    const bar=document.createElement('div');
    bar.style.cssText='display:flex;align-items:center;margin:4px 0;font-size:12px';
    bar.innerHTML='<span style="width:80px">'+VERSIONS[i]+'</span><div style="background:'+colors[i%4]+';height:16px;width:'+(v/max*300)+'px;margin:0 8px"></div><span>'+v.toFixed(4)+'</span>';
    div.appendChild(bar);
  }});
  root.appendChild(div);
}}
</script></body></html>"""


def _git_commit_hash() -> str | None:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL, text=True,
        )
        return out.strip() or None
    except (OSError, subprocess.CalledProcessError):
        return None


SwingEvaluator = SwingBenchmarkEvaluator

"""Benchmark evaluation with causal, one-to-one swing matching."""

from __future__ import annotations

import csv
import json
import logging
import statistics
import subprocess
from pathlib import Path
from typing import Any

from shared.types.models import Candle
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
        candles: list[Candle] | None = None,
        bar_count: int | None = None,
    ) -> EvaluationReport:
        """Match predictions to truth and calculate location and semantic metrics.

        Matching is chronological and one-to-one.  The dynamic program first
        maximises the number of valid matches and then minimises total time and
        price error, avoiding the arbitrary pairings produced by greedy search.
        """
        ec = self._config.evaluation
        pip = pip_size_for_symbol(symbol, self._config)
        index_tol = ec.index_match_tolerance_bars
        price_tol = self._price_tolerance(symbol, candles)
        confirmed = [swing for swing in predicted if swing.confirmed]

        pair_indexes = self._ordered_match(
            confirmed,
            ground_truth,
            index_tolerance=index_tol,
            price_tolerance=price_tol,
            pip_size=pip,
        )
        matched_pred = {pred_index for pred_index, _ in pair_indexes}
        matched_gt = {truth_index for _, truth_index in pair_indexes}

        pairs: list[dict[str, Any]] = []
        delays: list[float] = []
        relative_delays: list[float] = []
        price_errors: list[float] = []
        time_errors: list[float] = []
        for pred_index, truth_index in pair_indexes:
            pred = confirmed[pred_index]
            truth = ground_truth[truth_index]
            price_error = abs(pred.price - truth.price) / max(pip, 1e-12)
            time_error = abs(pred.pivot_index - truth.pivot_index)
            pred_confirmation = (
                pred.confirmation_index
                if pred.confirmation_index is not None
                else pred.pivot_index + pred.confirmation_delay
            )
            if truth.confirmed_at_index is not None:
                relative_delay = pred_confirmation - truth.confirmed_at_index
                delay = relative_delay
            else:
                relative_delay = pred.confirmation_delay
                delay = pred.confirmation_delay
            delays.append(float(delay))
            relative_delays.append(float(relative_delay))
            price_errors.append(price_error)
            time_errors.append(float(time_error))
            index_component = time_error / max(index_tol, 1)
            price_component = abs(pred.price - truth.price) / max(price_tol, 1e-12)
            pairs.append(
                {
                    "predicted_index": pred.pivot_index,
                    "ground_truth_index": truth.pivot_index,
                    "predicted_confirmation_index": pred_confirmation,
                    "ground_truth_confirmation_index": truth.confirmed_at_index,
                    "delay_bars": delay,
                    "relative_detection_delay_bars": relative_delay,
                    "price_error_pips": round(price_error, 3),
                    "time_error_bars": time_error,
                    "match_cost": round(index_component + price_component, 6),
                    "tier_match": pred.tier == truth.tier,
                    "scope_match": pred.scope == truth.scope,
                    "full_semantic_match": pred.tier == truth.tier and pred.scope == truth.scope,
                    "predicted_direction": pred.direction.value,
                    "ground_truth_direction": truth.direction.value,
                    "predicted_tier": pred.tier.value,
                    "ground_truth_tier": truth.tier.value,
                    "predicted_scope": pred.scope.value,
                    "ground_truth_scope": truth.scope.value,
                    "predicted_hierarchy_state": (
                        pred.hierarchy_state.value
                        if pred.hierarchy_state is not None
                        else None
                    ),
                    "predicted_hierarchy_confirmation_index": (
                        pred.hierarchy_confirmation_index
                    ),
                    "predicted_hierarchy_revision_index": pred.hierarchy_revision_index,
                    "label_id": truth.label_id,
                    "sample_id": truth.sample_id,
                }
            )

        tp = len(pair_indexes)
        fp = len(confirmed) - tp
        fn = len(ground_truth) - tp
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

        semantic_tp = sum(1 for pair in pairs if pair["full_semantic_match"])
        semantic_precision = (
            semantic_tp / len(confirmed) if confirmed else 0.0
        )
        semantic_recall = (
            semantic_tp / len(ground_truth) if ground_truth else 0.0
        )
        semantic_f1 = _f1(semantic_precision, semantic_recall)

        major = self._semantic_subset_metrics(
            confirmed, ground_truth, pair_indexes, "tier", SwingTier.MAJOR
        )
        external = self._semantic_subset_metrics(
            confirmed, ground_truth, pair_indexes, "scope", SwingScope.EXTERNAL
        )
        major_external = self._compound_subset_metrics(confirmed, ground_truth, pair_indexes)
        tier_accuracy = (
            sum(1 for pred_i, truth_i in pair_indexes if confirmed[pred_i].tier == ground_truth[truth_i].tier)
            / tp
            if tp
            else 0.0
        )
        scope_accuracy = (
            sum(1 for pred_i, truth_i in pair_indexes if confirmed[pred_i].scope == ground_truth[truth_i].scope)
            / tp
            if tp
            else 0.0
        )
        major_external_f1 = _f1(major_external[0], major_external[1])
        average_confidence = (
            sum(swing.confidence for swing in confirmed) / len(confirmed) if confirmed else 0.0
        )
        average_strength = (
            sum(swing.strength for swing in confirmed) / len(confirmed) if confirmed else 0.0
        )
        effective_bar_count = bar_count if bar_count is not None else (len(candles) if candles else 0)

        report = EvaluationReport(
            precision=precision,
            recall=recall,
            f1_score=f1,
            false_positives=fp,
            false_negatives=fn,
            true_positives=tp,
            average_detection_delay_bars=sum(delays) / len(delays) if delays else 0.0,
            average_price_error_pips=sum(price_errors) / len(price_errors) if price_errors else 0.0,
            average_time_error_bars=sum(time_errors) / len(time_errors) if time_errors else 0.0,
            major_precision=major[0],
            major_recall=major[1],
            external_precision=external[0],
            external_recall=external[1],
            major_external_precision=major_external[0],
            major_external_recall=major_external[1],
            major_external_f1=major_external_f1,
            semantic_precision=semantic_precision,
            semantic_recall=semantic_recall,
            semantic_f1=semantic_f1,
            semantic_true_positives=semantic_tp,
            tier_accuracy=tier_accuracy,
            scope_accuracy=scope_accuracy,
            false_positives_per_1000_bars=(
                1000.0 * fp / effective_bar_count if effective_bar_count else 0.0
            ),
            average_relative_detection_delay_bars=(
                sum(relative_delays) / len(relative_delays) if relative_delays else 0.0
            ),
            average_confidence=average_confidence,
            average_strength=average_strength,
            repainting_rate=self._repainting_rate(confirmed),
            matched_pairs=pairs,
            metadata={
                "symbol": symbol,
                "predicted": len(confirmed),
                "ground_truth": len(ground_truth),
                "engine_version": engine_version,
                "benchmark_version": benchmark_version,
                "regime": regime,
                "runtime_ms": runtime_ms,
                "bar_count": effective_bar_count,
                "index_match_tolerance_bars": index_tol,
                "price_match_tolerance": price_tol,
                "price_match_tolerance_pips": price_tol / max(pip, 1e-12),
                "matching": "ordered_maximum_cardinality_minimum_cost",
                "commit_hash": _git_commit_hash(),
                "config_snapshot": {
                    "pivot_lookback": self._config.pivot.left_lookback,
                    "confirmation_delay": self._config.confirmation.delay_bars,
                },
            },
        )
        log_stage("evaluation", len(confirmed), tp, f1=round(f1, 4))
        return report

    def _price_tolerance(self, symbol: str, candles: list[Candle] | None) -> float:
        ec = self._config.evaluation
        base = pips_to_price(ec.price_match_tolerance_pips, symbol, self._config)
        if not candles:
            return base
        true_ranges: list[float] = []
        previous_close = candles[0].close
        spreads: list[float] = []
        for candle in candles:
            true_ranges.append(
                max(
                    candle.high - candle.low,
                    abs(candle.high - previous_close),
                    abs(candle.low - previous_close),
                )
            )
            previous_close = candle.close
            if candle.spread is not None and candle.spread >= 0:
                spreads.append(candle.spread)
        atr_proxy = statistics.median(true_ranges) if true_ranges else 0.0
        spread_proxy = statistics.median(spreads) if spreads else 0.0
        return max(base, 0.05 * atr_proxy, 2.0 * spread_proxy)

    def _ordered_match(
        self,
        predicted: list[DetectedSwing],
        truth: list[BenchmarkLabel],
        *,
        index_tolerance: int,
        price_tolerance: float,
        pip_size: float,
    ) -> list[tuple[int, int]]:
        n, m = len(predicted), len(truth)
        # score = (number_of_matches, total_cost); higher match count wins,
        # lower cost breaks ties.
        dp: list[list[tuple[int, float]]] = [
            [(0, 0.0) for _ in range(m + 1)] for _ in range(n + 1)
        ]
        choice: list[list[str]] = [["" for _ in range(m + 1)] for _ in range(n + 1)]

        def better(left: tuple[int, float], right: tuple[int, float]) -> bool:
            return left[0] > right[0] or (left[0] == right[0] and left[1] < right[1] - 1e-12)

        for i in range(n - 1, -1, -1):
            for j in range(m - 1, -1, -1):
                best = dp[i + 1][j]
                action = "SKIP_PRED"
                if better(dp[i][j + 1], best):
                    best = dp[i][j + 1]
                    action = "SKIP_TRUTH"
                pred, label = predicted[i], truth[j]
                index_error = abs(pred.pivot_index - label.pivot_index)
                price_error = abs(pred.price - label.price)
                if (
                    pred.direction == label.direction
                    and index_error <= index_tolerance
                    and price_error <= price_tolerance
                ):
                    cost = (
                        index_error / max(index_tolerance, 1)
                        + price_error / max(price_tolerance, pip_size, 1e-12)
                    )
                    tail = dp[i + 1][j + 1]
                    matched = (tail[0] + 1, tail[1] + cost)
                    # Prefer a valid match when count and cost are exactly tied.
                    if better(matched, best) or matched == best:
                        best = matched
                        action = "MATCH"
                dp[i][j] = best
                choice[i][j] = action

        matches: list[tuple[int, int]] = []
        i = j = 0
        while i < n and j < m:
            action = choice[i][j]
            if action == "MATCH":
                matches.append((i, j))
                i += 1
                j += 1
            elif action == "SKIP_TRUTH":
                j += 1
            else:
                i += 1
        return matches

    def _semantic_subset_metrics(self, predicted, truth, pairs, attr, value):
        semantic_tp = sum(
            1
            for pred_index, truth_index in pairs
            if getattr(predicted[pred_index], attr) == value
            and getattr(truth[truth_index], attr) == value
        )
        predicted_count = sum(1 for item in predicted if getattr(item, attr) == value)
        truth_count = sum(1 for item in truth if getattr(item, attr) == value)
        precision = semantic_tp / predicted_count if predicted_count else 0.0
        recall = semantic_tp / truth_count if truth_count else 0.0
        return precision, recall

    def _compound_subset_metrics(self, predicted, truth, pairs):
        def qualifies(item) -> bool:
            return item.tier is SwingTier.MAJOR and item.scope is SwingScope.EXTERNAL

        semantic_tp = sum(
            1
            for pred_index, truth_index in pairs
            if qualifies(predicted[pred_index]) and qualifies(truth[truth_index])
        )
        predicted_count = sum(1 for item in predicted if qualifies(item))
        truth_count = sum(1 for item in truth if qualifies(item))
        return (
            semantic_tp / predicted_count if predicted_count else 0.0,
            semantic_tp / truth_count if truth_count else 0.0,
        )

    def _repainting_rate(self, swings: list[DetectedSwing]) -> float:
        if not swings:
            return 0.0
        unconfirmed = sum(1 for swing in swings if not swing.confirmed)
        return unconfirmed / len(swings)


def _f1(precision: float, recall: float) -> float:
    return 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0


def write_json_report(report: EvaluationReport, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    return path


def write_csv_report(report: EvaluationReport, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["metric", "value"])
        for key, value in report.to_dict().items():
            if key not in ("matched_pairs", "metadata"):
                writer.writerow([key, value])
    return path


def write_markdown_report(report: EvaluationReport, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_markdown_summary(report), encoding="utf-8")
    return path


def write_comparison_charts(reports: dict[str, EvaluationReport], path: Path) -> Path:
    """Write HTML bar charts comparing versions."""
    path.parent.mkdir(parents=True, exist_ok=True)
    versions = list(reports.keys())
    metrics = [
        "precision",
        "recall",
        "f1_score",
        "semantic_f1",
        "major_external_f1",
        "major_precision",
        "external_precision",
    ]
    charts = {metric: [getattr(reports[version], metric) for version in versions] for metric in metrics}
    path.write_text(_comparison_chart_html(versions, charts), encoding="utf-8")
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
        "| Metric | Value |",
        "|--------|-------|",
        f"| Precision | {report.precision:.4f} |",
        f"| Recall | {report.recall:.4f} |",
        f"| F1 | {report.f1_score:.4f} |",
        f"| False Positives | {report.false_positives} |",
        f"| False Negatives | {report.false_negatives} |",
        f"| False Positives / 1,000 bars | {report.false_positives_per_1000_bars:.2f} |",
        f"| Relative Detection Delay (bars) | {report.average_relative_detection_delay_bars:.2f} |",
        f"| Price Error (pips) | {report.average_price_error_pips:.2f} |",
        f"| Time Error (bars) | {report.average_time_error_bars:.2f} |",
        "",
        "## Structural Classification",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Major External F1 | {report.major_external_f1:.4f} |",
        f"| Major External Precision | {report.major_external_precision:.4f} |",
        f"| Major External Recall | {report.major_external_recall:.4f} |",
        f"| Full Semantic F1 | {report.semantic_f1:.4f} |",
        f"| Full Semantic Precision | {report.semantic_precision:.4f} |",
        f"| Full Semantic Recall | {report.semantic_recall:.4f} |",
        f"| Full Semantic True Positives | {report.semantic_true_positives} |",
        f"| Major Precision | {report.major_precision:.4f} |",
        f"| Major Recall | {report.major_recall:.4f} |",
        f"| External Precision | {report.external_precision:.4f} |",
        f"| External Recall | {report.external_recall:.4f} |",
        f"| Tier Accuracy | {report.tier_accuracy:.4f} |",
        f"| Scope Accuracy | {report.scope_accuracy:.4f} |",
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
<h1>Version Comparison</h1><div id="charts"></div><script>
const VERSIONS={versions_js};const DATA={bars_js};const colors=['#22c55e','#3b82f6','#f59e0b','#ef4444'];
const root=document.getElementById('charts');for(const [metric,values] of Object.entries(DATA)){{
 const max=Math.max(...values,0.01),div=document.createElement('div');div.className='chart';div.innerHTML='<h2>'+metric+'</h2>';
 values.forEach((v,i)=>{{const bar=document.createElement('div');bar.style.cssText='display:flex;align-items:center;margin:4px 0;font-size:12px';
 bar.innerHTML='<span style="width:80px">'+VERSIONS[i]+'</span><div style="background:'+colors[i%4]+';height:16px;width:'+(v/max*300)+'px;margin:0 8px"></div><span>'+v.toFixed(4)+'</span>';div.appendChild(bar)}});root.appendChild(div)}}
</script></body></html>"""


def _git_commit_hash() -> str | None:
    try:
        output = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return output.strip() or None
    except (OSError, subprocess.CalledProcessError):
        return None


SwingEvaluator = SwingBenchmarkEvaluator

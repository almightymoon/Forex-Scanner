"""Benchmark evaluation framework with JSON/CSV report export."""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from typing import Any

from swing_engine.config import get_config
from swing_engine.models import (
    BenchmarkLabel,
    DetectedSwing,
    EvaluationReport,
    SwingScope,
    SwingTier,
)

logger = logging.getLogger("fxnav.swing_engine.evaluation")


class SwingBenchmarkEvaluator:
    """Reusable evaluator for comparing predicted swings to ground truth."""

    def __init__(self, config=None):
        self._config = config or get_config()

    def evaluate(
        self,
        predicted: list[DetectedSwing],
        ground_truth: list[BenchmarkLabel],
        symbol: str,
    ) -> EvaluationReport:
        from scanner.swing_detection.utils import pip_size_for_symbol, pips_to_price

        ec = self._config.evaluation
        price_tol = pips_to_price(ec.price_match_tolerance_pips, symbol, self._config)
        index_tol = ec.index_match_tolerance_bars
        pip = pip_size_for_symbol(symbol, self._config)

        confirmed = [s for s in predicted if s.confirmed]
        matched_gt: set[int] = set()
        matched_pred: set[int] = set()
        pairs: list[dict[str, Any]] = []
        delays: list[int] = []
        price_errors: list[float] = []
        time_errors: list[int] = []

        for pi, pred in enumerate(confirmed):
            best_gi = None
            best_score = float("inf")
            for gi, label in enumerate(ground_truth):
                if gi in matched_gt or pred.direction.value != label.direction.value:
                    continue
                idx_diff = abs(pred.pivot_index - label.pivot_index)
                price_diff = abs(pred.price - label.price)
                if idx_diff <= index_tol and price_diff <= price_tol:
                    score = idx_diff + price_diff / max(pip, 1e-12)
                    if score < best_score:
                        best_score = score
                        best_gi = gi

            if best_gi is not None:
                label = ground_truth[best_gi]
                matched_gt.add(best_gi)
                matched_pred.add(pi)
                delays.append(pred.confirmation_delay)
                price_errors.append(abs(pred.price - label.price) / pip)
                time_errors.append(abs(pred.pivot_index - label.pivot_index))
                pairs.append({
                    "predicted_index": pred.pivot_index,
                    "ground_truth_index": label.pivot_index,
                    "delay_bars": pred.confirmation_delay,
                    "price_error_pips": round(abs(pred.price - label.price) / pip, 2),
                    "time_error_bars": abs(pred.pivot_index - label.pivot_index),
                    "tier_match": pred.tier == label.tier,
                    "scope_match": pred.scope == label.scope,
                })

        tp = len(matched_pred)
        fp = len(confirmed) - tp
        fn = len(ground_truth) - len(matched_gt)
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

        major_tp, major_fp, major_fn = self._tier_metrics(confirmed, ground_truth, matched_pred, matched_gt, SwingTier.MAJOR)
        ext_tp, ext_fp, ext_fn = self._scope_metrics(confirmed, ground_truth, matched_pred, matched_gt, SwingScope.EXTERNAL)

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
            major_precision=major_tp / (major_tp + major_fp) if (major_tp + major_fp) else 0.0,
            major_recall=major_tp / (major_tp + major_fn) if (major_tp + major_fn) else 0.0,
            external_precision=ext_tp / (ext_tp + ext_fp) if (ext_tp + ext_fp) else 0.0,
            external_recall=ext_tp / (ext_tp + ext_fn) if (ext_tp + ext_fn) else 0.0,
            matched_pairs=pairs,
            metadata={"symbol": symbol, "predicted": len(confirmed), "ground_truth": len(ground_truth)},
        )
        logger.info("benchmark_evaluation", extra=report.to_dict())
        return report

    def _tier_metrics(self, predicted, ground_truth, matched_pred, matched_gt, tier):
        tp = sum(1 for i in matched_pred if predicted[i].tier == tier)
        fp = sum(1 for s in predicted if s.confirmed and s.tier == tier) - tp
        fn = sum(1 for i, g in enumerate(ground_truth) if g.tier == tier and i not in matched_gt)
        return tp, fp, fn

    def _scope_metrics(self, predicted, ground_truth, matched_pred, matched_gt, scope):
        tp = sum(1 for i in matched_pred if predicted[i].scope == scope)
        fp = sum(1 for s in predicted if s.confirmed and s.scope == scope) - tp
        fn = sum(1 for i, g in enumerate(ground_truth) if g.scope == scope and i not in matched_gt)
        return tp, fp, fn


def write_json_report(report: EvaluationReport, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    return path


def write_csv_report(report: EvaluationReport, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    summary = report.to_dict()
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["metric", "value"])
        for key in (
            "precision", "recall", "f1_score", "true_positives", "false_positives",
            "false_negatives", "average_detection_delay_bars", "average_price_error_pips",
            "average_time_error_bars", "major_precision", "major_recall",
            "external_precision", "external_recall",
        ):
            writer.writerow([key, summary[key]])
        writer.writerow([])
        writer.writerow(["matched_pairs"])
        if report.matched_pairs:
            writer.writerow(list(report.matched_pairs[0].keys()))
            for pair in report.matched_pairs:
                writer.writerow(list(pair.values()))
    return path

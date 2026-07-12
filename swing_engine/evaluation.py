"""Benchmark evaluation with JSON/CSV export."""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path

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

        report = EvaluationReport(
            precision=p, recall=r, f1_score=f1, false_positives=fp, false_negatives=fn, true_positives=tp,
            average_detection_delay_bars=sum(delays) / len(delays) if delays else 0.0,
            average_price_error_pips=sum(price_errors) / len(price_errors) if price_errors else 0.0,
            average_time_error_bars=sum(time_errors) / len(time_errors) if time_errors else 0.0,
            major_precision=mtp / (mtp + mfp) if (mtp + mfp) else 0.0,
            major_recall=mtp / (mtp + mfn) if (mtp + mfn) else 0.0,
            external_precision=etp / (etp + efp) if (etp + efp) else 0.0,
            external_recall=etp / (etp + efn) if (etp + efn) else 0.0,
            matched_pairs=pairs,
            metadata={"symbol": symbol, "predicted": len(confirmed), "ground_truth": len(ground_truth)},
        )
        log_stage("evaluation", len(confirmed), tp, f1=round(f1, 4))
        return report

    def _subset_metrics(self, predicted, ground_truth, matched_pred, matched_gt, attr, value):
        tp = sum(1 for i in matched_pred if getattr(predicted[i], attr) == value)
        fp = sum(1 for s in predicted if s.confirmed and getattr(s, attr) == value) - tp
        fn = sum(1 for i, g in enumerate(ground_truth) if getattr(g, attr) == value and i not in matched_gt)
        return tp, fp, fn


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
            if k != "matched_pairs" and k != "metadata":
                w.writerow([k, v])
    return path


SwingEvaluator = SwingBenchmarkEvaluator

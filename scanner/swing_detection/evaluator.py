"""Evaluate detected swings against benchmark labels."""

from __future__ import annotations

import logging

from scanner.swing_detection.models import BenchmarkSwing, EvaluationReport, Swing, SwingDirection
from scanner.swing_detection.utils import SwingDetectionConfig, log_stage, pip_size_for_symbol, pips_to_price

logger = logging.getLogger("fxnav.swing_detection.evaluator")


class SwingEvaluator:
    """Compare predicted swings to ground-truth benchmark labels."""

    def __init__(self, config: SwingDetectionConfig):
        self._config = config

    def evaluate(
        self,
        predicted: list[Swing],
        benchmark: list[BenchmarkSwing],
        symbol: str,
    ) -> EvaluationReport:
        """Match predictions to labels and compute metrics."""
        ec = self._config.evaluation
        price_tol = pips_to_price(ec.price_match_tolerance_pips, symbol, self._config)
        index_tol = ec.index_match_tolerance_bars

        confirmed = [s for s in predicted if s.confirmed]
        matched_benchmark: set[int] = set()
        matched_predicted: set[int] = set()
        pairs: list[dict] = []
        delays: list[int] = []
        price_errors: list[float] = []
        pip = pip_size_for_symbol(symbol, self._config)

        for pi, pred in enumerate(confirmed):
            best_bi = None
            best_score = float("inf")
            for bi, label in enumerate(benchmark):
                if bi in matched_benchmark:
                    continue
                if pred.direction != label.direction:
                    continue
                index_diff = abs(pred.pivot_index - label.pivot_index)
                price_diff = abs(pred.price - label.price)
                if index_diff <= index_tol and price_diff <= price_tol:
                    score = index_diff + price_diff / max(pip, 1e-12)
                    if score < best_score:
                        best_score = score
                        best_bi = bi

            if best_bi is not None:
                label = benchmark[best_bi]
                matched_benchmark.add(best_bi)
                matched_predicted.add(pi)
                delay = pred.confirmation_delay
                delays.append(delay)
                err_pips = abs(pred.price - label.price) / pip
                price_errors.append(err_pips)
                pairs.append(
                    {
                        "predicted_index": pred.pivot_index,
                        "benchmark_index": label.pivot_index,
                        "delay_bars": delay,
                        "price_error_pips": round(err_pips, 2),
                    }
                )

        tp = len(matched_predicted)
        fp = len(confirmed) - tp
        fn = len(benchmark) - len(matched_benchmark)

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

        report = EvaluationReport(
            precision=precision,
            recall=recall,
            f1_score=f1,
            average_detection_delay_bars=sum(delays) / len(delays) if delays else 0.0,
            average_price_error_pips=sum(price_errors) / len(price_errors) if price_errors else 0.0,
            false_positives=fp,
            false_negatives=fn,
            true_positives=tp,
            matched_pairs=pairs,
            metadata={
                "predicted_total": len(confirmed),
                "benchmark_total": len(benchmark),
            },
        )

        log_stage(
            "evaluation",
            len(confirmed),
            tp,
            precision=round(precision, 4),
            recall=round(recall, 4),
            f1=round(f1, 4),
            false_positives=fp,
            false_negatives=fn,
        )
        logger.info("evaluation_report", extra=report.to_dict())
        return report

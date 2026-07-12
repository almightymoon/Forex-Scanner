"""Parameter optimization framework (Sprint 4).

Grid-searches key swing-detection parameters against benchmark labels and ranks
results so thresholds are data-driven, not manually tweaked.
"""

from __future__ import annotations

import dataclasses
import itertools
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from shared.types.models import Timeframe

from swing_engine.config import SwingEngineConfig, get_config
from swing_engine.detector import SwingEngine
from swing_engine.evaluation import SwingBenchmarkEvaluator
from swing_engine.models import BenchmarkLabel, EvaluationReport


@dataclass
class ParamGrid:
    """Search space for optimizer."""

    pivot_left_lookback: tuple[int, ...] = (2, 3, 4)
    confirmation_delay_bars: tuple[int, ...] = (2, 3, 4)
    leg_min_atr_multiple: tuple[float, ...] = (0.25, 0.35, 0.45)
    quality_min_acceptable: tuple[float, ...] = (40.0, 50.0, 60.0)
    major_min_atr_multiple: tuple[float, ...] = (1.0, 1.2, 1.4)

    def combinations(self) -> Iterator[dict[str, Any]]:
        keys = [
            "pivot_left_lookback",
            "confirmation_delay_bars",
            "leg_min_atr_multiple",
            "quality_min_acceptable",
            "major_min_atr_multiple",
        ]
        values = [
            self.pivot_left_lookback,
            self.confirmation_delay_bars,
            self.leg_min_atr_multiple,
            self.quality_min_acceptable,
            self.major_min_atr_multiple,
        ]
        for combo in itertools.product(*values):
            yield dict(zip(keys, combo))


@dataclass
class OptimizationResult:
    params: dict[str, Any]
    report: EvaluationReport
    rank_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "params": self.params,
            "rank_score": round(self.rank_score, 4),
            "f1_score": round(self.report.f1_score, 4),
            "precision": round(self.report.precision, 4),
            "recall": round(self.report.recall, 4),
            "delay": round(self.report.average_detection_delay_bars, 2),
            "repainting_rate": round(self.report.repainting_rate, 4),
        }


def _apply_params(base: SwingEngineConfig, params: dict[str, Any]) -> SwingEngineConfig:
    pivot = dataclasses.replace(
        base.pivot,
        left_lookback=params["pivot_left_lookback"],
        right_lookback=params["pivot_left_lookback"],
    )
    confirmation = dataclasses.replace(base.confirmation, delay_bars=params["confirmation_delay_bars"])
    leg = dataclasses.replace(base.leg, min_atr_multiple=params["leg_min_atr_multiple"])
    quality = dataclasses.replace(base.quality, min_acceptable=params["quality_min_acceptable"])
    classification = dataclasses.replace(
        base.classification,
        major_min_atr_multiple=params["major_min_atr_multiple"],
    )
    return dataclasses.replace(
        base,
        pivot=pivot,
        confirmation=confirmation,
        leg=leg,
        quality=quality,
        classification=classification,
    )


def _rank_score(report: EvaluationReport) -> float:
    """Higher is better: F1 primary, penalize delay and repainting."""
    return (
        report.f1_score * 100
        - report.average_detection_delay_bars * 2
        - report.repainting_rate * 20
        + report.precision * 5
    )


def run_optimization(
    bars: list,
    ground_truth: list[BenchmarkLabel],
    *,
    symbol: str,
    timeframe: Timeframe,
    version: str = "1.3.0",
    grid: ParamGrid | None = None,
    max_combinations: int = 500,
) -> list[OptimizationResult]:
    """Evaluate parameter combinations and return ranked results."""
    grid = grid or ParamGrid()
    base_cfg = get_config(timeframe, version=version, symbol=symbol)
    results: list[OptimizationResult] = []

    for i, params in enumerate(grid.combinations()):
        if i >= max_combinations:
            break
        cfg = _apply_params(base_cfg, params)
        engine = SwingEngine(cfg, version=version)
        det = engine.detect(bars, symbol=symbol, timeframe=timeframe)
        report = SwingBenchmarkEvaluator(cfg).evaluate(
            det.confirmed_swings,
            ground_truth,
            symbol,
            engine_version=version,
            regime="optimize",
            runtime_ms=det.performance.runtime_ms if det.performance else None,
        )
        report.repainting_rate = det.artifacts.repainting_stats.get("repainting_rate", report.repainting_rate)
        score = _rank_score(report)
        results.append(OptimizationResult(params=params, report=report, rank_score=score))

    results.sort(key=lambda r: r.rank_score, reverse=True)
    return results


def save_optimization_report(
    results: list[OptimizationResult],
    path: Path,
    *,
    top_n: int = 20,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.utcnow().isoformat(),
        "total_combinations": len(results),
        "top_results": [r.to_dict() for r in results[:top_n]],
        "best_params": results[0].params if results else {},
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path

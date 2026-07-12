"""Benchmark dataset catalog and suite runner."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from shared.types.models import Candle, Timeframe

from swing_engine.calibration import CalibrationReport, calibrate_confidence
from swing_engine.config import get_config
from swing_engine.detector import SwingEngine
from swing_engine.evaluation import SwingBenchmarkEvaluator
from swing_engine.models import BenchmarkLabel, EvaluationReport, SwingDirection, SwingScope, SwingTier
from swing_engine.regression import append_history, load_history, write_regression_dashboard

MANIFEST_PATH = Path(__file__).resolve().parents[1] / "benchmarks" / "datasets" / "manifest.json"
LABELS_DIR = Path(__file__).resolve().parents[1] / "benchmarks" / "labels"
HISTORY_PATH = Path(__file__).resolve().parents[1] / "benchmarks" / "history" / "regression_history.jsonl"
DASHBOARD_PATH = Path(__file__).resolve().parents[1] / "benchmarks" / "reports" / "regression_dashboard.html"


@dataclass
class DatasetSpec:
    id: str
    symbol: str
    timeframe: str
    regime: str
    bars: int
    labels_file: str
    min_f1: float = 0.85
    min_major_f1: float = 0.0
    min_major_precision: float = 0.0
    min_major_recall: float = 0.0
    human_review: bool = False
    label_source: str = "engine"
    evaluation_tolerance_bars: int = 0
    description: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DatasetSpec":
        return cls(
            id=data["id"],
            symbol=data["symbol"],
            timeframe=data["timeframe"],
            regime=data["regime"],
            bars=int(data.get("bars", 120)),
            labels_file=data["labels_file"],
            min_f1=float(data.get("min_f1", 0.85)),
            min_major_f1=float(data.get("min_major_f1", 0.0)),
            min_major_precision=float(data.get("min_major_precision", 0.0)),
            min_major_recall=float(data.get("min_major_recall", 0.0)),
            human_review=bool(data.get("human_review", False)),
            label_source=data.get("label_source", "engine"),
            evaluation_tolerance_bars=int(data.get("evaluation_tolerance_bars", 0)),
            description=data.get("description", ""),
        )


@dataclass
class DatasetResult:
    spec: DatasetSpec
    report: EvaluationReport
    passed: bool
    swing_count: int = 0
    major_f1: float = 0.0
    calibration: CalibrationReport | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.spec.id,
            "symbol": self.spec.symbol,
            "timeframe": self.spec.timeframe,
            "regime": self.spec.regime,
            "human_review": self.spec.human_review,
            "label_source": self.spec.label_source,
            "passed": self.passed,
            "min_f1": self.spec.min_f1,
            "f1_score": round(self.report.f1_score, 4),
            "precision": round(self.report.precision, 4),
            "recall": round(self.report.recall, 4),
            "false_positives": self.report.false_positives,
            "false_negatives": self.report.false_negatives,
            "delay": round(self.report.average_detection_delay_bars, 2),
            "repainting_rate": round(self.report.repainting_rate, 4),
            "swing_count": self.swing_count,
            "major_precision": round(self.report.major_precision, 4),
            "major_recall": round(self.report.major_recall, 4),
            "major_f1": round(self.major_f1, 4),
            "external_precision": round(self.report.external_precision, 4),
            "external_recall": round(self.report.external_recall, 4),
        }
        if self.calibration:
            out["calibration_error"] = round(self.calibration.mean_calibration_error, 4)
        return out


@dataclass
class BenchmarkSuiteReport:
    version: str
    results: list[DatasetResult] = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat(timespec="seconds"))

    @property
    def all_passed(self) -> bool:
        return all(r.passed for r in self.results)

    def to_dict(self) -> dict[str, Any]:
        human = [r for r in self.results if r.spec.human_review]
        return {
            "version": self.version,
            "generated_at": self.generated_at,
            "all_passed": self.all_passed,
            "datasets": [r.to_dict() for r in self.results],
            "by_regime": _group_avg(self.results, "regime"),
            "by_symbol": _group_avg(self.results, "symbol"),
            "human_review": {
                "count": len(human),
                "avg_major_f1": sum(r.major_f1 for r in human) / len(human) if human else 0.0,
                "avg_major_precision": sum(r.report.major_precision for r in human) / len(human) if human else 0.0,
                "avg_major_recall": sum(r.report.major_recall for r in human) / len(human) if human else 0.0,
            },
        }


def load_manifest(path: Path = MANIFEST_PATH) -> list[DatasetSpec]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [DatasetSpec.from_dict(d) for d in data.get("datasets", [])]


def load_labels(path: Path) -> tuple[list[BenchmarkLabel], dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    labels = []
    for item in data.get("swings", []):
        labels.append(BenchmarkLabel(
            pivot_index=item["pivot_index"],
            timestamp=datetime.fromisoformat(item["timestamp"]),
            price=item["price"],
            direction=SwingDirection(item["direction"]),
            tier=SwingTier(item.get("tier", "MAJOR")),
            scope=SwingScope(item.get("scope", "EXTERNAL")),
        ))
    return labels, data


def write_labels(
    path: Path,
    *,
    symbol: str,
    timeframe: str,
    regime: str,
    swings: list,
    source_version: str,
    description: str = "",
    label_source: str = "engine",
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "symbol": symbol,
        "timeframe": timeframe,
        "regime": regime,
        "benchmark_version": "2.0",
        "label_source": label_source,
        "source_engine": source_version,
        "description": description,
        "generated_at": datetime.utcnow().isoformat(timespec="seconds"),
        "swings": [
            {
                "pivot_index": s.pivot_index,
                "timestamp": s.timestamp.isoformat(),
                "price": round(s.price, 6),
                "direction": s.direction.value,
                "tier": s.tier.value,
                "scope": s.scope.value,
            }
            for s in swings
        ],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _major_f1(report: EvaluationReport) -> float:
    mp, mr = report.major_precision, report.major_recall
    return 2 * mp * mr / (mp + mr) if (mp + mr) else 0.0


def _passes_thresholds(spec: DatasetSpec, report: EvaluationReport, major_f1: float) -> bool:
    if spec.human_review:
        if spec.min_major_precision and report.major_precision < spec.min_major_precision:
            return False
        if spec.min_major_recall and report.major_recall < spec.min_major_recall:
            return False
        if spec.min_major_f1 and major_f1 < spec.min_major_f1:
            return False
        return True
    return report.f1_score >= spec.min_f1


def run_dataset(
    spec: DatasetSpec,
    bars: list[Candle],
    *,
    version: str,
    bar_loader: Callable[[DatasetSpec], list[Candle]] | None = None,
) -> DatasetResult:
    if bar_loader:
        bars = bar_loader(spec)
    tf = Timeframe(spec.timeframe)
    cfg = get_config(tf, version=version, symbol=spec.symbol)
    engine = SwingEngine(cfg, version=version)
    result = engine.detect(bars, symbol=spec.symbol, timeframe=tf)
    labels_path = LABELS_DIR / spec.labels_file
    ground_truth, _ = load_labels(labels_path)
    runtime = result.performance.runtime_ms if result.performance else None
    import dataclasses
    eval_cfg = cfg
    if spec.evaluation_tolerance_bars:
        ev = dataclasses.replace(cfg.evaluation, index_match_tolerance_bars=spec.evaluation_tolerance_bars)
        eval_cfg = dataclasses.replace(cfg, evaluation=ev)
    report = SwingBenchmarkEvaluator(eval_cfg).evaluate(
        result.confirmed_swings,
        ground_truth,
        spec.symbol,
        engine_version=version,
        benchmark_version=spec.label_source,
        regime=spec.regime,
        runtime_ms=runtime,
    )
    if result.artifacts.repainting_stats:
        report.repainting_rate = result.artifacts.repainting_stats.get(
            "repainting_rate", report.repainting_rate
        )
    report.metadata["human_review"] = spec.human_review
    report.metadata["label_source"] = spec.label_source
    report.metadata["major_f1"] = round(_major_f1(report), 4)
    report.metadata["dataset_id"] = spec.id

    major_f1 = _major_f1(report)
    passed = _passes_thresholds(spec, report, major_f1)
    calibration = calibrate_confidence(
        result.confirmed_swings, ground_truth, cfg, symbol=spec.symbol,
    )
    return DatasetResult(
        spec=spec,
        report=report,
        passed=passed,
        swing_count=len(result.confirmed_swings),
        major_f1=major_f1,
        calibration=calibration,
    )


def run_suite(
    specs: list[DatasetSpec],
    bar_loader: Callable[[DatasetSpec], list[Candle]],
    *,
    version: str,
    append_to_history: bool = True,
    write_dashboard: bool = True,
) -> BenchmarkSuiteReport:
    suite = BenchmarkSuiteReport(version=version)
    for spec in specs:
        bars = bar_loader(spec)
        result = run_dataset(spec, bars, version=version)
        suite.results.append(result)
        if append_to_history:
            entry = append_history(result.report, HISTORY_PATH)
            result.report.metadata["history_timestamp"] = entry.timestamp
    if write_dashboard and HISTORY_PATH.exists():
        write_regression_dashboard(load_history(HISTORY_PATH), DASHBOARD_PATH)
    return suite


def _group_avg(results: list[DatasetResult], key: str) -> dict[str, dict[str, float]]:
    groups: dict[str, list[DatasetResult]] = {}
    for r in results:
        k = getattr(r.spec, key)
        groups.setdefault(k, []).append(r)
    out: dict[str, dict[str, float]] = {}
    for k, items in groups.items():
        n = len(items) or 1
        out[k] = {
            "count": float(len(items)),
            "f1": sum(i.report.f1_score for i in items) / n,
            "precision": sum(i.report.precision for i in items) / n,
            "recall": sum(i.report.recall for i in items) / n,
            "major_f1": sum(i.major_f1 for i in items) / n,
            "major_precision": sum(i.report.major_precision for i in items) / n,
            "major_recall": sum(i.report.major_recall for i in items) / n,
            "delay": sum(i.report.average_detection_delay_bars for i in items) / n,
        }
    return out

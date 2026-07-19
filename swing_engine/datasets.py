"""Benchmark dataset catalog, immutable data loading, and suite runner."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from shared.types.models import Candle, Timeframe

from swing_engine.annotations import PROTECTED_ANNOTATION_ORIGINS, labels_from_document, load_annotation_document
from swing_engine.benchmark_data import BenchmarkDataError, load_candles_csv
from swing_engine.calibration import CalibrationReport, calibrate_confidence
from swing_engine.config import get_config
from swing_engine.detector import SwingEngine
from swing_engine.evaluation import SwingBenchmarkEvaluator
from swing_engine.models import BenchmarkLabel, EvaluationReport
from swing_engine.regression import append_history, load_history, write_regression_dashboard

REPO_ROOT = Path(__file__).resolve().parents[1]
BENCHMARKS_DIR = REPO_ROOT / "benchmarks"
MANIFEST_PATH = BENCHMARKS_DIR / "datasets" / "manifest.json"
LABELS_DIR = BENCHMARKS_DIR / "labels"
DATA_DIR = BENCHMARKS_DIR / "data"
HISTORY_PATH = BENCHMARKS_DIR / "history" / "regression_history.jsonl"
DASHBOARD_PATH = BENCHMARKS_DIR / "reports" / "regression_dashboard.html"


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
    source_type: str = "synthetic"
    data_file: str | None = None
    data_sha256: str | None = None
    source_start_index: int | None = None
    source_end_index: int | None = None
    labelable_start_index: int | None = None
    labelable_end_index: int | None = None
    sample_id: str | None = None
    split: str = "REGRESSION"
    label_origin: str = "BOOTSTRAP"
    enabled: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DatasetSpec":
        return cls(
            id=data["id"],
            symbol=data["symbol"],
            timeframe=data["timeframe"],
            regime=data.get("regime", "unknown"),
            bars=int(data.get("bars", 0)),
            labels_file=data["labels_file"],
            min_f1=float(data.get("min_f1", 0.85)),
            min_major_f1=float(data.get("min_major_f1", 0.0)),
            min_major_precision=float(data.get("min_major_precision", 0.0)),
            min_major_recall=float(data.get("min_major_recall", 0.0)),
            human_review=bool(data.get("human_review", False)),
            label_source=data.get("label_source", "engine"),
            evaluation_tolerance_bars=int(data.get("evaluation_tolerance_bars", 0)),
            description=data.get("description", ""),
            source_type=data.get("source_type", "synthetic"),
            data_file=data.get("data_file"),
            data_sha256=data.get("data_sha256"),
            source_start_index=(
                int(data["source_start_index"])
                if data.get("source_start_index") is not None
                else None
            ),
            source_end_index=(
                int(data["source_end_index"])
                if data.get("source_end_index") is not None
                else None
            ),
            labelable_start_index=(
                int(data["labelable_start_index"])
                if data.get("labelable_start_index") is not None
                else None
            ),
            labelable_end_index=(
                int(data["labelable_end_index"])
                if data.get("labelable_end_index") is not None
                else None
            ),
            sample_id=data.get("sample_id"),
            split=data.get("split", "REGRESSION"),
            label_origin=data.get("label_origin", "BOOTSTRAP"),
            enabled=bool(data.get("enabled", True)),
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
            "split": self.spec.split,
            "source_type": self.spec.source_type,
            "label_origin": self.spec.label_origin,
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
    generated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )

    @property
    def all_passed(self) -> bool:
        return all(result.passed for result in self.results)

    def to_dict(self) -> dict[str, Any]:
        human = [result for result in self.results if result.spec.human_review]
        return {
            "version": self.version,
            "generated_at": self.generated_at,
            "all_passed": self.all_passed,
            "datasets": [result.to_dict() for result in self.results],
            "by_regime": _group_avg(self.results, "regime"),
            "by_symbol": _group_avg(self.results, "symbol"),
            "by_split": _group_avg(self.results, "split"),
            "human_review": {
                "count": len(human),
                "avg_major_f1": sum(r.major_f1 for r in human) / len(human) if human else 0.0,
                "avg_major_precision": (
                    sum(r.report.major_precision for r in human) / len(human) if human else 0.0
                ),
                "avg_major_recall": (
                    sum(r.report.major_recall for r in human) / len(human) if human else 0.0
                ),
            },
        }


def load_manifest(path: Path = MANIFEST_PATH, *, include_disabled: bool = False) -> list[DatasetSpec]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    specs = [DatasetSpec.from_dict(item) for item in data.get("datasets", [])]
    return specs if include_disabled else [spec for spec in specs if spec.enabled]


def _labels_path(
    spec_or_path: DatasetSpec | Path,
    *,
    manifest_path: Path = MANIFEST_PATH,
) -> Path:
    if isinstance(spec_or_path, DatasetSpec):
        path = Path(spec_or_path.labels_file)
    else:
        path = Path(spec_or_path)

    if path.is_absolute():
        return path

    if isinstance(spec_or_path, DatasetSpec):
        package_path = (
            Path(manifest_path).parent / path
        ).resolve()

        if package_path.exists():
            return package_path

    return LABELS_DIR / path


def load_labels(
    path: Path,
    *,
    sample_id: str | None = None,
    confirmed_only: bool = True,
) -> tuple[list[BenchmarkLabel], dict[str, Any]]:
    document = load_annotation_document(path)
    return (
        labels_from_document(document, sample_id=sample_id, confirmed_only=confirmed_only),
        document,
    )


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
    allow_human_overwrite: bool = False,
) -> Path:
    """Write bootstrap labels while protecting all human annotation files."""
    path = Path(path)
    if path.name.endswith(".human.json") and not allow_human_overwrite:
        raise PermissionError(f"Refusing to write engine labels into human benchmark: {path}")
    if path.exists() and not allow_human_overwrite:
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing.get("label_origin") in PROTECTED_ANNOTATION_ORIGINS:
            raise PermissionError(f"Refusing to overwrite human benchmark: {path}")

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "symbol": symbol,
        "timeframe": timeframe,
        "regime": regime,
        "benchmark_version": "2.0",
        "label_origin": "ENGINE_BOOTSTRAP",
        "label_source": label_source,
        "source_engine": source_version,
        "description": description,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "swings": [
            {
                "pivot_index": swing.pivot_index,
                "timestamp": swing.timestamp.isoformat(),
                "price": round(swing.price, 6),
                "direction": swing.direction.value,
                "tier": swing.tier.value,
                "scope": swing.scope.value,
            }
            for swing in swings
        ],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def resolve_data_path(
    spec: DatasetSpec,
    *,
    manifest_path: Path = MANIFEST_PATH,
) -> Path:
    if not spec.data_file:
        raise BenchmarkDataError(
            f"Dataset {spec.id} does not declare data_file"
        )

    path = Path(spec.data_file)

    if path.is_absolute():
        return path

    package_path = (
        Path(manifest_path).parent / path
    ).resolve()

    if package_path.exists():
        return package_path

    return (
        Path(manifest_path).parent.parent / path
    ).resolve()


def load_real_bars(spec: DatasetSpec, *, manifest_path: Path = MANIFEST_PATH) -> list[Candle]:
    if spec.source_type not in {"file", "real"}:
        raise BenchmarkDataError(f"Dataset {spec.id} is not a real-file dataset")
    return load_candles_csv(
        resolve_data_path(spec, manifest_path=manifest_path),
        symbol=spec.symbol,
        timeframe=spec.timeframe,
        expected_sha256=spec.data_sha256,
        start_index=spec.source_start_index,
        end_index=spec.source_end_index,
    )


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
    bars: list[Candle] | None = None,
    *,
    version: str,
    bar_loader: Callable[[DatasetSpec], list[Candle]] | None = None,
    manifest_path: Path = MANIFEST_PATH,
) -> DatasetResult:
    if bar_loader is not None:
        bars = bar_loader(spec)
    elif bars is None:
        bars = load_real_bars(spec, manifest_path=manifest_path)
    if not bars:
        raise BenchmarkDataError(f"Dataset {spec.id} loaded no bars")

    timeframe = Timeframe(spec.timeframe)
    config = get_config(timeframe, version=version, symbol=spec.symbol)
    engine = SwingEngine(config, version=version)
    result = engine.detect(bars, symbol=spec.symbol, timeframe=timeframe)

    labels_path = _labels_path(
        spec,
        manifest_path=manifest_path,
    )
    ground_truth, label_document = load_labels(labels_path, sample_id=spec.sample_id)
    predictions = result.confirmed_swings
    if spec.labelable_start_index is not None:
        predictions = [
            swing for swing in predictions if swing.pivot_index >= spec.labelable_start_index
        ]
        ground_truth = [
            label for label in ground_truth if label.pivot_index >= spec.labelable_start_index
        ]
    if spec.labelable_end_index is not None:
        predictions = [
            swing for swing in predictions if swing.pivot_index <= spec.labelable_end_index
        ]
        ground_truth = [
            label for label in ground_truth if label.pivot_index <= spec.labelable_end_index
        ]

    runtime = result.performance.runtime_ms if result.performance else None
    import dataclasses

    eval_cfg = config
    if spec.evaluation_tolerance_bars:
        ev = dataclasses.replace(
            config.evaluation, index_match_tolerance_bars=spec.evaluation_tolerance_bars
        )
        eval_cfg = dataclasses.replace(config, evaluation=ev)
    report = SwingBenchmarkEvaluator(eval_cfg).evaluate(
        predictions,
        ground_truth,
        spec.symbol,
        engine_version=version,
        benchmark_version=label_document.get("benchmark_version", spec.label_source),
        regime=spec.regime,
        runtime_ms=runtime,
        candles=bars,
        bar_count=len(bars),
    )
    if result.artifacts.repainting_stats:
        report.repainting_rate = result.artifacts.repainting_stats.get(
            "repainting_rate", report.repainting_rate
        )
    report.metadata.update(
        {
            "human_review": spec.human_review,
            "label_source": spec.label_source,
            "dataset_id": spec.id,
            "sample_id": spec.sample_id,
            "split": spec.split,
            "source_type": spec.source_type,
            "label_origin": label_document.get("label_origin", spec.label_origin),
            "labelable_start_index": spec.labelable_start_index,
            "labelable_end_index": spec.labelable_end_index,
        }
    )
    major_f1 = _major_f1(report)
    report.metadata["major_f1"] = round(major_f1, 4)
    passed = _passes_thresholds(spec, report, major_f1)
    calibration = calibrate_confidence(
        predictions, ground_truth, config, symbol=spec.symbol,
    )
    return DatasetResult(
        spec=spec,
        report=report,
        passed=passed,
        swing_count=len(predictions),
        major_f1=major_f1,
        calibration=calibration,
    )


def run_suite(
    specs: list[DatasetSpec],
    bar_loader: Callable[[DatasetSpec], list[Candle]] | None = None,
    *,
    version: str,
    append_to_history: bool = True,
    write_dashboard: bool = True,
    manifest_path: Path = MANIFEST_PATH,
) -> BenchmarkSuiteReport:
    suite = BenchmarkSuiteReport(version=version)
    for spec in specs:
        result = run_dataset(
            spec, version=version, bar_loader=bar_loader, manifest_path=manifest_path
        )
        suite.results.append(result)
        if append_to_history:
            entry = append_history(result.report, HISTORY_PATH)
            result.report.metadata["history_timestamp"] = entry.timestamp
    if write_dashboard and HISTORY_PATH.exists():
        write_regression_dashboard(load_history(HISTORY_PATH), DASHBOARD_PATH)
    return suite


def _group_avg(results: list[DatasetResult], key: str) -> dict[str, dict[str, float]]:
    groups: dict[str, list[DatasetResult]] = {}
    for result in results:
        value = getattr(result.spec, key)
        groups.setdefault(value, []).append(result)
    output: dict[str, dict[str, float]] = {}
    for value, items in groups.items():
        count = len(items) or 1
        output[value] = {
            "count": float(len(items)),
            "f1": sum(item.report.f1_score for item in items) / count,
            "precision": sum(item.report.precision for item in items) / count,
            "recall": sum(item.report.recall for item in items) / count,
            "major_f1": sum(item.major_f1 for item in items) / count,
            "major_precision": sum(item.report.major_precision for item in items) / count,
            "major_recall": sum(item.report.major_recall for item in items) / count,
            "delay": sum(item.report.average_detection_delay_bars for item in items) / count,
        }
    return output

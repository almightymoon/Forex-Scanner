"""Benchmark dataset catalog and suite runner."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from shared.types.models import Candle, Timeframe

from swing_engine.config import get_config
from swing_engine.detector import SwingEngine
from swing_engine.evaluation import SwingBenchmarkEvaluator
from swing_engine.models import BenchmarkLabel, EvaluationReport, SwingDirection, SwingScope, SwingTier

MANIFEST_PATH = Path(__file__).resolve().parents[1] / "benchmarks" / "datasets" / "manifest.json"
LABELS_DIR = Path(__file__).resolve().parents[1] / "benchmarks" / "labels"


@dataclass
class DatasetSpec:
    id: str
    symbol: str
    timeframe: str
    regime: str
    bars: int
    labels_file: str
    min_f1: float = 0.85
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
            description=data.get("description", ""),
        )


@dataclass
class DatasetResult:
    spec: DatasetSpec
    report: EvaluationReport
    passed: bool
    swing_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.spec.id,
            "symbol": self.spec.symbol,
            "timeframe": self.spec.timeframe,
            "regime": self.spec.regime,
            "passed": self.passed,
            "min_f1": self.spec.min_f1,
            "f1_score": round(self.report.f1_score, 4),
            "precision": round(self.report.precision, 4),
            "recall": round(self.report.recall, 4),
            "delay": round(self.report.average_detection_delay_bars, 2),
            "repainting_rate": round(self.report.repainting_rate, 4),
            "swing_count": self.swing_count,
            "major_precision": round(self.report.major_precision, 4),
            "minor_precision": round(self.report.external_precision, 4),
        }


@dataclass
class BenchmarkSuiteReport:
    version: str
    results: list[DatasetResult] = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat(timespec="seconds"))

    @property
    def all_passed(self) -> bool:
        return all(r.passed for r in self.results)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "generated_at": self.generated_at,
            "all_passed": self.all_passed,
            "datasets": [r.to_dict() for r in self.results],
            "by_regime": _group_avg(self.results, "regime"),
            "by_symbol": _group_avg(self.results, "symbol"),
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
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "symbol": symbol,
        "timeframe": timeframe,
        "regime": regime,
        "benchmark_version": "1.0",
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
    report = SwingBenchmarkEvaluator(cfg).evaluate(
        result.confirmed_swings,
        ground_truth,
        spec.symbol,
        engine_version=version,
        benchmark_version="dataset",
        regime=spec.regime,
        runtime_ms=runtime,
    )
    if result.artifacts.repainting_stats:
        report.repainting_rate = result.artifacts.repainting_stats.get(
            "repainting_rate", report.repainting_rate
        )
    passed = report.f1_score >= spec.min_f1
    return DatasetResult(spec=spec, report=report, passed=passed, swing_count=len(result.confirmed_swings))


def run_suite(
    specs: list[DatasetSpec],
    bar_loader: Callable[[DatasetSpec], list[Candle]],
    *,
    version: str,
) -> BenchmarkSuiteReport:
    suite = BenchmarkSuiteReport(version=version)
    for spec in specs:
        bars = bar_loader(spec)
        suite.results.append(run_dataset(spec, bars, version=version))
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
            "delay": sum(i.report.average_detection_delay_bars for i in items) / n,
        }
    return out

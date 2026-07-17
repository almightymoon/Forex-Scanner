"""Human swing annotation documents, templates, and quality assurance."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from shared.types.models import Candle, Timeframe

from swing_engine.benchmark_data import BenchmarkDataError, load_candles_csv, sha256_file
from swing_engine.benchmark_sampling import BenchmarkWindow
from swing_engine.models import BenchmarkLabel, SwingDirection, SwingScope, SwingTier


HUMAN_ORIGINS = {"HUMAN", "HUMAN_DRAFT", "HUMAN_ADJUDICATED"}


@dataclass(frozen=True)
class AnnotationIssue:
    severity: str
    code: str
    message: str
    sample_id: str | None = None
    label_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "sample_id": self.sample_id,
            "label_id": self.label_id,
        }


def parse_datetime(value: str | None) -> datetime | None:
    if value is None or not str(value).strip():
        return None
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def benchmark_label_from_dict(item: dict[str, Any]) -> BenchmarkLabel:
    return BenchmarkLabel(
        pivot_index=int(item["pivot_index"]),
        timestamp=parse_datetime(item["timestamp"]) or datetime.min.replace(tzinfo=timezone.utc),
        price=float(item["price"]),
        direction=SwingDirection(item["direction"]),
        tier=SwingTier(item.get("tier", "MAJOR")),
        scope=SwingScope(item.get("scope", "EXTERNAL")),
        label_id=item.get("label_id"),
        sample_id=item.get("sample_id"),
        source_bar_index=(
            int(item["source_bar_index"]) if item.get("source_bar_index") is not None else None
        ),
        price_field=item.get("price_field"),
        confirmation_status=item.get("confirmation_status", "CONFIRMED"),
        confirmed_at_index=(
            int(item["confirmed_at_index"])
            if item.get("confirmed_at_index") is not None
            else None
        ),
        confirmed_at_timestamp=parse_datetime(item.get("confirmed_at_timestamp")),
        strength=int(item["strength"]) if item.get("strength") is not None else None,
        quality_score=(
            float(item["quality_score"]) if item.get("quality_score") is not None else None
        ),
        confidence=float(item["confidence"]) if item.get("confidence") is not None else None,
        tags=tuple(str(tag) for tag in item.get("tags", [])),
        notes=str(item.get("notes", "")),
        annotator_id=item.get("annotator_id"),
        review_status=item.get("review_status", "RAW"),
    )


def load_annotation_document(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def labels_from_document(
    document: dict[str, Any],
    *,
    sample_id: str | None = None,
    confirmed_only: bool = True,
) -> list[BenchmarkLabel]:
    labels = [benchmark_label_from_dict(item) for item in document.get("swings", [])]
    if sample_id is not None:
        labels = [label for label in labels if label.sample_id in (None, sample_id)]
    if confirmed_only:
        labels = [
            label
            for label in labels
            if label.confirmation_status in {"CONFIRMED", "ADJUDICATED"}
        ]
    return labels


def _sample_to_dict(window: BenchmarkWindow, candles: list[Candle]) -> dict[str, Any]:
    start = candles[window.source_start_index]
    end = candles[window.source_end_index]
    return {
        **window.to_dict(),
        "start_timestamp": start.timestamp.isoformat(),
        "end_timestamp": end.timestamp.isoformat(),
    }


def write_human_annotation_template(
    path: Path,
    *,
    dataset_id: str,
    symbol: str,
    timeframe: str,
    data_file: str,
    data_sha256: str,
    candles: list[Candle],
    windows: Iterable[BenchmarkWindow],
    source: str,
    price_basis: str,
    label_policy_version: str = "SWING_POLICY_1.0",
) -> Path:
    """Create an empty, versioned human annotation pack."""
    path = Path(path)
    if path.exists():
        existing = load_annotation_document(path)
        if existing.get("label_origin") in HUMAN_ORIGINS and existing.get("swings"):
            raise FileExistsError(f"Refusing to overwrite non-empty human labels: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    window_list = list(windows)
    payload = {
        "benchmark_id": f"{symbol}_{timeframe}_HUMAN_V1",
        "benchmark_version": "1.0.0-draft",
        "label_policy_version": label_policy_version,
        "label_origin": "HUMAN_DRAFT",
        "status": "DRAFT",
        "dataset": {
            "dataset_id": dataset_id,
            "symbol": symbol,
            "timeframe": timeframe,
            "timezone": "UTC",
            "price_basis": price_basis,
            "source": source,
            "data_file": data_file,
            "data_sha256": data_sha256,
            "bar_count": len(candles),
            "first_timestamp": candles[0].timestamp.isoformat(),
            "last_timestamp": candles[-1].timestamp.isoformat(),
        },
        "samples": [_sample_to_dict(window, candles) for window in window_list],
        "swings": [],
        "review": {
            "required_annotators": 2,
            "adjudicator": None,
            "adjudicated_at": None,
            "notes": "Blind-label first. Predictions must remain hidden until labels are frozen.",
        },
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def resolve_dataset_path(annotation_path: Path, document: dict[str, Any]) -> Path:
    raw = document.get("dataset", {}).get("data_file")
    if not raw:
        raise BenchmarkDataError("Annotation document has no dataset.data_file")
    path = Path(raw)
    if path.is_absolute():
        return path
    return (Path(annotation_path).parent / path).resolve()


def validate_annotation_document(path: Path) -> list[AnnotationIssue]:
    """Validate label integrity against the immutable candle file."""
    path = Path(path)
    document = load_annotation_document(path)
    issues: list[AnnotationIssue] = []
    dataset = document.get("dataset", {})
    symbol = dataset.get("symbol") or document.get("symbol")
    timeframe = dataset.get("timeframe") or document.get("timeframe")
    if not symbol or not timeframe:
        return [AnnotationIssue("ERROR", "DATASET_IDENTITY", "Missing symbol or timeframe")]

    try:
        data_path = resolve_dataset_path(path, document)
        candles = load_candles_csv(
            data_path,
            symbol=symbol,
            timeframe=Timeframe(timeframe),
            expected_sha256=dataset.get("data_sha256"),
        )
    except (BenchmarkDataError, OSError, ValueError) as exc:
        return [AnnotationIssue("ERROR", "DATASET_LOAD", str(exc))]

    if dataset.get("bar_count") is not None and int(dataset["bar_count"]) != len(candles):
        issues.append(
            AnnotationIssue(
                "ERROR",
                "BAR_COUNT",
                f"Manifest says {dataset['bar_count']} bars, file contains {len(candles)}",
            )
        )

    samples: dict[str, dict[str, Any]] = {}
    for sample in document.get("samples", []):
        sample_id = sample.get("sample_id")
        if not sample_id or sample_id in samples:
            issues.append(
                AnnotationIssue("ERROR", "SAMPLE_ID", "Sample IDs must exist and be unique", sample_id)
            )
            continue
        samples[sample_id] = sample
        start = int(sample.get("source_start_index", -1))
        end = int(sample.get("source_end_index", -1))
        label_start = int(sample.get("labelable_start_index", -1))
        label_end = int(sample.get("labelable_end_index", -1))
        window_length = end - start + 1
        if start < 0 or end < start or end >= len(candles):
            issues.append(AnnotationIssue("ERROR", "SAMPLE_RANGE", "Invalid source range", sample_id))
        if label_start < 0 or label_end < label_start or label_end >= window_length:
            issues.append(
                AnnotationIssue("ERROR", "LABELABLE_RANGE", "Invalid labelable range", sample_id)
            )

    seen_labels: set[str] = set()
    labels_by_sample: dict[str, list[BenchmarkLabel]] = {}
    for raw in document.get("swings", []):
        try:
            label = benchmark_label_from_dict(raw)
        except (KeyError, TypeError, ValueError) as exc:
            issues.append(AnnotationIssue("ERROR", "LABEL_PARSE", str(exc), raw.get("sample_id"), raw.get("label_id")))
            continue
        label_id = label.label_id or ""
        if not label_id or label_id in seen_labels:
            issues.append(
                AnnotationIssue(
                    "ERROR",
                    "LABEL_ID",
                    "Label IDs must exist and be unique",
                    label.sample_id,
                    label.label_id,
                )
            )
        seen_labels.add(label_id)
        sample = samples.get(label.sample_id or "")
        if sample is None:
            issues.append(
                AnnotationIssue(
                    "ERROR", "UNKNOWN_SAMPLE", "Label references an unknown sample", label.sample_id, label.label_id
                )
            )
            continue

        local_index = label.pivot_index
        source_start = int(sample["source_start_index"])
        source_index = source_start + local_index
        labelable_start = int(sample["labelable_start_index"])
        labelable_end = int(sample["labelable_end_index"])
        if local_index < labelable_start or local_index > labelable_end:
            issues.append(
                AnnotationIssue(
                    "ERROR",
                    "OUTSIDE_LABELABLE_WINDOW",
                    f"Pivot index {local_index} is outside [{labelable_start}, {labelable_end}]",
                    label.sample_id,
                    label.label_id,
                )
            )
            continue
        if source_index >= len(candles):
            issues.append(AnnotationIssue("ERROR", "PIVOT_RANGE", "Pivot exceeds data file", label.sample_id, label.label_id))
            continue
        candle = candles[source_index]
        if label.source_bar_index is not None and label.source_bar_index != source_index:
            issues.append(
                AnnotationIssue(
                    "ERROR",
                    "SOURCE_INDEX",
                    f"source_bar_index should be {source_index}",
                    label.sample_id,
                    label.label_id,
                )
            )
        if label.timestamp != candle.timestamp:
            issues.append(
                AnnotationIssue(
                    "ERROR",
                    "TIMESTAMP",
                    f"Label timestamp {label.timestamp.isoformat()} != candle {candle.timestamp.isoformat()}",
                    label.sample_id,
                    label.label_id,
                )
            )
        expected_price = candle.high if label.direction is SwingDirection.HIGH else candle.low
        tolerance = max(1e-8, abs(expected_price) * 1e-9)
        if abs(label.price - expected_price) > tolerance:
            issues.append(
                AnnotationIssue(
                    "ERROR",
                    "PRICE",
                    f"{label.direction.value} price should be {expected_price}, got {label.price}",
                    label.sample_id,
                    label.label_id,
                )
            )
        expected_field = "HIGH" if label.direction is SwingDirection.HIGH else "LOW"
        if label.price_field and label.price_field.upper() != expected_field:
            issues.append(
                AnnotationIssue(
                    "ERROR", "PRICE_FIELD", f"price_field should be {expected_field}", label.sample_id, label.label_id
                )
            )
        if label.confirmation_status in {"CONFIRMED", "ADJUDICATED"}:
            if label.confirmed_at_index is None:
                issues.append(
                    AnnotationIssue(
                        "ERROR", "CONFIRMATION_INDEX", "Confirmed label needs confirmed_at_index", label.sample_id, label.label_id
                    )
                )
            elif label.confirmed_at_index <= label.pivot_index:
                issues.append(
                    AnnotationIssue(
                        "ERROR", "CONFIRMATION_ORDER", "Confirmation must occur after the pivot", label.sample_id, label.label_id
                    )
                )
            else:
                confirmation_source_index = source_start + label.confirmed_at_index
                if confirmation_source_index > int(sample["source_end_index"]):
                    issues.append(
                        AnnotationIssue(
                            "ERROR", "CONFIRMATION_RANGE", "Confirmation exceeds sample context", label.sample_id, label.label_id
                        )
                    )
                elif label.confirmed_at_timestamp != candles[confirmation_source_index].timestamp:
                    issues.append(
                        AnnotationIssue(
                            "ERROR",
                            "CONFIRMATION_TIMESTAMP",
                            "Confirmation timestamp does not match confirmation candle",
                            label.sample_id,
                            label.label_id,
                        )
                    )
        if label.strength is not None and not 1 <= label.strength <= 5:
            issues.append(AnnotationIssue("ERROR", "STRENGTH", "Strength must be 1..5", label.sample_id, label.label_id))
        if label.quality_score is not None and not 0 <= label.quality_score <= 100:
            issues.append(AnnotationIssue("ERROR", "QUALITY", "Quality must be 0..100", label.sample_id, label.label_id))
        if label.confidence is not None and not 0 <= label.confidence <= 1:
            issues.append(AnnotationIssue("ERROR", "CONFIDENCE", "Confidence must be 0..1", label.sample_id, label.label_id))
        if label.review_status == "ADJUDICATED" and label.scope is SwingScope.NEUTRAL:
            issues.append(
                AnnotationIssue(
                    "ERROR", "NEUTRAL_FINAL", "Adjudicated labels cannot use NEUTRAL scope", label.sample_id, label.label_id
                )
            )
        if label.confidence is not None and label.confidence < 0.5:
            issues.append(
                AnnotationIssue("WARNING", "LOW_CONFIDENCE", "Low-confidence label needs review", label.sample_id, label.label_id)
            )
        labels_by_sample.setdefault(label.sample_id or "", []).append(label)

    for sample_id, labels in labels_by_sample.items():
        ordered = sorted(labels, key=lambda item: item.pivot_index)
        for previous, current in zip(ordered, ordered[1:]):
            if (
                previous.direction is current.direction
                and previous.tier is SwingTier.MAJOR
                and current.tier is SwingTier.MAJOR
            ):
                issues.append(
                    AnnotationIssue(
                        "WARNING",
                        "CONSECUTIVE_MAJOR_DIRECTION",
                        "Consecutive major swings have the same direction",
                        sample_id,
                        current.label_id,
                    )
                )

    if document.get("label_origin") == "HUMAN_ADJUDICATED" and not document.get("swings"):
        issues.append(AnnotationIssue("ERROR", "EMPTY_ADJUDICATED", "Adjudicated benchmark has no labels"))
    return issues


def document_data_checksum(path: Path) -> str:
    document = load_annotation_document(path)
    return sha256_file(resolve_dataset_path(path, document))

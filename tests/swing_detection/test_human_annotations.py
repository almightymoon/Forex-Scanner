import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from shared.types.models import Candle, Timeframe
from swing_engine.annotations import validate_annotation_document, write_human_annotation_template
from swing_engine.benchmark_data import sha256_file, write_canonical_candles_csv
from swing_engine.benchmark_sampling import BenchmarkWindow
from swing_engine.datasets import write_labels


def _candles(count: int = 400) -> list[Candle]:
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    result = []
    for index in range(count):
        base = 2600.0 + index * 0.1
        result.append(
            Candle(
                symbol="XAUUSD",
                timeframe=Timeframe.H1,
                timestamp=start + timedelta(hours=index),
                open=base,
                high=base + 2.0,
                low=base - 1.5,
                close=base + 0.5,
                tick_volume=100,
                spread=0.2,
            )
        )
    return result


def _template(tmp_path: Path) -> Path:
    candles = _candles()
    data_path = write_canonical_candles_csv(
        tmp_path / "data.csv.gz", candles, source="TEST"
    )
    labels_path = tmp_path / "XAUUSD_H1.human.json"
    window = BenchmarkWindow(
        sample_id="XAUUSD_H1_001",
        source_start_index=0,
        source_end_index=399,
        labelable_start_index=50,
        labelable_end_index=349,
        split="TRAIN",
        primary_regime="TREND",
    )
    write_human_annotation_template(
        labels_path,
        dataset_id="TEST_XAU_H1",
        symbol="XAUUSD",
        timeframe="H1",
        data_file="data.csv.gz",
        data_sha256=sha256_file(data_path),
        candles=candles,
        windows=[window],
        source="TEST",
        price_basis="MID",
    )
    return labels_path


def test_valid_human_label_matches_exact_candle(tmp_path: Path):
    labels_path = _template(tmp_path)
    document = json.loads(labels_path.read_text())
    candle = _candles()[100]
    document["swings"] = [
        {
            "label_id": "XAUUSD_H1_001_SWG_001",
            "sample_id": "XAUUSD_H1_001",
            "pivot_index": 100,
            "source_bar_index": 100,
            "timestamp": candle.timestamp.isoformat(),
            "price": candle.high,
            "price_field": "HIGH",
            "direction": "HIGH",
            "tier": "MAJOR",
            "scope": "EXTERNAL",
            "confirmation_status": "CONFIRMED",
            "confirmed_at_index": 105,
            "confirmed_at_timestamp": _candles()[105].timestamp.isoformat(),
            "strength": 4,
            "quality_score": 90,
            "confidence": 0.95,
            "tags": [],
            "review_status": "RAW",
            "notes": "test",
        }
    ]
    labels_path.write_text(json.dumps(document, indent=2))
    assert not [issue for issue in validate_annotation_document(labels_path) if issue.severity == "ERROR"]


def test_validator_catches_wrong_pivot_price(tmp_path: Path):
    labels_path = _template(tmp_path)
    document = json.loads(labels_path.read_text())
    candle = _candles()[100]
    document["swings"] = [
        {
            "label_id": "BAD",
            "sample_id": "XAUUSD_H1_001",
            "pivot_index": 100,
            "timestamp": candle.timestamp.isoformat(),
            "price": candle.high + 1,
            "direction": "HIGH",
            "tier": "MAJOR",
            "scope": "EXTERNAL",
            "confirmation_status": "CONFIRMED",
            "confirmed_at_index": 105,
            "confirmed_at_timestamp": _candles()[105].timestamp.isoformat(),
        }
    ]
    labels_path.write_text(json.dumps(document, indent=2))
    codes = {issue.code for issue in validate_annotation_document(labels_path)}
    assert "PRICE" in codes


def test_engine_bootstrap_cannot_overwrite_human_file(tmp_path: Path):
    labels_path = _template(tmp_path)
    try:
        write_labels(
            labels_path,
            symbol="XAUUSD",
            timeframe="H1",
            regime="trend",
            swings=[],
            source_version="2.0.0",
        )
    except PermissionError:
        pass
    else:
        raise AssertionError("human label protection did not fire")


def test_ai_assisted_draft_is_protected_from_engine_overwrite(tmp_path: Path):
    labels_path = tmp_path / "draft.json"
    labels_path.write_text(
        json.dumps(
            {
                "label_origin": "AI_ASSISTED_EXPERT_DRAFT",
                "swings": [{"label_id": "draft-label"}],
            }
        )
    )

    try:
        write_labels(
            labels_path,
            symbol="XAUUSD",
            timeframe="H1",
            regime="trend",
            swings=[],
            source_version="2.0.0",
        )
    except PermissionError:
        pass
    else:
        raise AssertionError("AI-assisted label protection did not fire")

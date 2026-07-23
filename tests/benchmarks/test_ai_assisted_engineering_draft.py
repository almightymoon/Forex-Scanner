"""Focused tests for AI-assisted engineering-draft freeze and evaluator."""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def load_script(filename: str, module_name: str):
    path = ROOT / "scripts" / filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


FREEZER = load_script(
    "freeze_xauusd_h1_2022_2024_ai_assisted_draft.py",
    "test_ai_draft_freezer",
)
EVALUATOR = load_script(
    "evaluate_xauusd_h1_2022_2024_ai_assisted_engineering.py",
    "test_ai_draft_evaluator",
)

from shared.types.models import Candle, Timeframe  # noqa: E402
from swing_engine.benchmark_data import write_canonical_candles_csv  # noqa: E402


CANDIDATE_COMMIT = "3fd5d7c74b82c3728d7badaa6cd72044bdd6bd1d"
# Abandoned blind template — must not live in the repository or be required by tests.
PASS1_REPO_PATH = (
    ROOT
    / "benchmarks/data/locked/XAUUSD/H1/retrospective_2022_2024/labels/pass_1.json"
)
SELECTION = (
    ROOT
    / "benchmarks/data/locked/XAUUSD/H1/retrospective_2022_2024/windows_v1/"
    / "selection_manifest.json"
)
WINDOWS_ROOT = SELECTION.parent

# Historical SHA of the empty DRAFT human template (not a repository fixture).
EXPECTED_PASS1 = (
    "d1fe3440c0cc21eb888a07caadeb6893830c0354b7341b8157a64debca1bd0ca"
)
FROZEN_AI_PACKAGE = (
    ROOT / "benchmarks/data/engineering/XAUUSD/H1_2022_2024_ai_draft_v1"
)
EXPECTED_SELECTION = (
    "9bdaa635b71b09287def03bd38a0a8fe3c1a50a5f0fd431ee686e685bbc369e8"
)
EXPECTED_WINDOWS = {
    "window_01_1224_1416.csv": (
        "5775bb6e9c02024d9ea9415c595044787b7c0ad5fea7b4b4738ff1c33c2482e2"
    ),
    "window_02_3769_3961.csv": (
        "a6ca7513b5165bbf8700aa2cd1c441cb21601ae967b294eb217acb856eeea1b1"
    ),
    "window_03_6315_6507.csv": (
        "e845c5b1249b237719322cae5382fba18c140ac302a1458e28b8c349469de91f"
    ),
    "window_04_8860_9052.csv": (
        "46512a8c4ec6230443bb9fec46b9db6522b4e3b6516ca26b3f5bc8fc97fdf133"
    ),
    "window_05_11405_11597.csv": (
        "7ba245bec20e133e33cabf7f13b0e996f6de8f6fc1a98e26ef9eef152055dbbd"
    ),
    "window_06_13951_14143.csv": (
        "a2e68346d9957ce3c54851dac0ca16f1b84a1d6de1c2e2ab2c8157355454740f"
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: dict) -> Path:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    return path


def make_window_csv(path: Path, *, start: datetime, bars: int = 192) -> list[dict]:
    rows = []
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "window_bar_index",
                "global_bar_index",
                "timestamp_utc",
                "open",
                "high",
                "low",
                "close",
                "tick_volume",
                "volume",
                "mean_spread",
                "source",
                "price_basis",
            ],
        )
        writer.writeheader()
        for index in range(bars):
            base = 1800.0 + index * 0.1
            high = f"{base + 2:.10f}"
            low = f"{base - 2:.10f}"
            ts = (start + timedelta(hours=index)).strftime("%Y-%m-%dT%H:%M:%SZ")
            row = {
                "window_bar_index": str(index),
                "global_bar_index": str(1000 + index),
                "timestamp_utc": ts,
                "open": f"{base:.10f}",
                "high": high,
                "low": low,
                "close": f"{base + 0.2:.10f}",
                "tick_volume": "10",
                "volume": "0",
                "mean_spread": "0.1000000000",
                "source": "SYNTHETIC",
                "price_basis": "BID",
            }
            writer.writerow(row)
            rows.append(row)
    return rows


def build_label(
    *,
    window_number: int,
    seq: int,
    pivot: int,
    direction: str,
    confirmed: int,
    row: dict,
    conf_row: dict,
    tier: str = "MINOR",
    scope: str = "INTERNAL",
    confidence: str = "HIGH",
) -> dict:
    field = "high" if direction == "HIGH" else "low"
    return {
        "label_id": f"AI_DRAFT_W{window_number:02d}_{seq:03d}",
        "window_number": window_number,
        "pivot_index": pivot,
        "timestamp_utc": row["timestamp_utc"],
        "price": row[field],
        "price_field": field,
        "direction": direction,
        "tier": tier,
        "scope": scope,
        "confirmed_at_index": confirmed,
        "confirmed_at_timestamp": conf_row["timestamp_utc"],
        "confidence": confidence,
        "notes": "synthetic",
        "origin": "AI_ASSISTED_ENGINEERING_DRAFT",
        "eligible_for_human_benchmark": False,
    }


def create_synthetic_draft_and_selection(tmp_path: Path) -> tuple[Path, Path]:
    """Create a minimal valid 6-window AI draft with expected counts."""
    selection_root = tmp_path / "selection"
    draft_root = tmp_path / "draft"
    selection_root.mkdir()
    draft_root.mkdir()

    expected_counts = {1: 4, 2: 8, 3: 4, 4: 9, 5: 6, 6: 11}
    windows = []
    all_labels = []
    start = datetime(2022, 1, 3, tzinfo=timezone.utc)

    for wi in range(1, 7):
        fname = f"window_{wi:02d}_0_192.csv"
        path = selection_root / fname
        rows = make_window_csv(
            path, start=start + timedelta(days=wi * 20)
        )
        digest = sha256(path)
        windows.append(
            {
                "window_number": wi,
                "bucket_start_index": 0,
                "bucket_end_index_exclusive": 100,
                "bucket_bars": 100,
                "start_index": 0,
                "end_index_exclusive": 192,
                "bars": 192,
                "first_utc": rows[0]["timestamp_utc"],
                "last_utc": rows[-1]["timestamp_utc"],
                "file": fname,
                "sha256": digest,
            }
        )
        count = expected_counts[wi]
        # Build alternating labels with enough separation.
        pivots = []
        cursor = 10
        direction = "HIGH"
        for seq in range(1, count + 1):
            pivot = cursor
            confirmed = pivot + 1
            pivots.append((pivot, direction, confirmed, seq))
            direction = "LOW" if direction == "HIGH" else "HIGH"
            cursor += 8
        for pivot, direction, confirmed, seq in pivots:
            tier = "MAJOR" if seq == 1 else "MINOR"
            scope = "EXTERNAL" if tier == "MAJOR" else "INTERNAL"
            all_labels.append(
                build_label(
                    window_number=wi,
                    seq=seq,
                    pivot=pivot,
                    direction=direction,
                    confirmed=confirmed,
                    row=rows[pivot],
                    conf_row=rows[confirmed],
                    tier=tier,
                    scope=scope,
                )
            )

    selection = {
        "selection_id": "SYNTHETIC_AI_DRAFT_SELECTION",
        "benchmark_type": "RETROSPECTIVE_HOLDOUT",
        "protocol_id": FREEZER.PROTOCOL_ID,
        "protocol_sha256": "0" * 64,
        "algorithm_version": "PRICE_BLIND_SIX_BUCKET_CENTERED_V1",
        "source_root": "synthetic",
        "canonical_source": "synthetic.csv.gz",
        "canonical_source_sha256": "0" * 64,
        "source_bar_count": 1152,
        "windows": windows,
        "window_files": {w["file"]: w["sha256"] for w in windows},
        "contamination_controls": {
            "labels_loaded": False,
            "predictions_loaded": False,
            "swing_engine_executed": False,
            "candidate_evaluated": False,
            "baseline_evaluated": False,
            "ohlc_inspected_for_selection": False,
            "selection_uses_prices_or_predictions": False,
        },
        "eligibility": {
            "eligible_for_tuning": False,
            "eligible_for_labeling": True,
            "eligible_for_evaluation": False,
            "prospective_test": False,
        },
    }
    write_json(selection_root / "selection_manifest.json", selection)

    labels_doc = {
        "origin": "AI_ASSISTED_ENGINEERING_DRAFT",
        "eligible_for_human_benchmark": False,
        "labels": all_labels,
        "label_count_total": len(all_labels),
        "label_count_by_window": {
            str(k): v for k, v in expected_counts.items()
        },
        "windows": {
            f"window_{i:02d}": [
                lab for lab in all_labels if lab["window_number"] == i
            ]
            for i in range(1, 7)
        },
    }
    write_json(draft_root / "ai_assisted_labels.json", labels_doc)
    write_json(
        draft_root / "methodology.json",
        {"classification": "AI_ASSISTED_ENGINEERING_DRAFT", "process": []},
    )
    (draft_root / "review.md").write_text(
        "# AI-assisted draft review\n\nAI_ASSISTED_ENGINEERING_DRAFT\n",
        encoding="utf-8",
    )
    for i in range(1, 7):
        (draft_root / f"annotated_window_{i:02d}.svg").write_text(
            f"<svg>window {i}</svg>\n",
            encoding="utf-8",
        )
    return draft_root, selection_root


def patch_expected_selection(monkeypatch: pytest.MonkeyPatch, selection_root: Path):
    digest = sha256(selection_root / "selection_manifest.json")
    monkeypatch.setattr(FREEZER, "EXPECTED_SELECTION_SHA", digest)
    monkeypatch.setattr(EVALUATOR, "EXPECTED_SELECTION_SHA", digest)


def aggregate(location_f1: float, semantic_f1: float) -> dict:
    return {
        "location": {"f1": location_f1, "precision": location_f1, "recall": location_f1},
        "semantic": {"f1": semantic_f1, "precision": semantic_f1, "recall": semantic_f1},
    }


def create_frozen_ai_package(tmp_path: Path) -> dict:
    package = tmp_path / "ai-package"
    package.mkdir()
    protocol_path = tmp_path / "protocol.json"
    protocol = {
        "protocol_id": FREEZER.PROTOCOL_ID,
        "benchmark_type": "RETROSPECTIVE_HOLDOUT",
        "candidate": {"version": "2.3.0-rc1", "commit": CANDIDATE_COMMIT},
        "baseline": {"version": "2.2.0"},
        "engineering_gates": {
            "prefix_stability_failures_max": 0,
            "location_f1_min": 0.75,
            "semantic_f1_min": 0.60,
        },
    }
    write_json(protocol_path, protocol)

    data_path = package / EVALUATOR.DATA_FILENAME
    labels_path = package / EVALUATOR.LABELS_FILENAME
    manifest_path = package / EVALUATOR.MANIFEST_FILENAME
    receipt_path = package / "freeze_receipt.json"

    start = datetime(2022, 6, 1, tzinfo=timezone.utc)
    candles = []
    for index in range(192 * 6):
        base = 1800.0 + index * 0.05
        candles.append(
            Candle(
                symbol="XAUUSD",
                timeframe=Timeframe.H1,
                timestamp=start + timedelta(hours=index),
                open=base,
                high=base + 2.0,
                low=base - 2.0,
                close=base + 0.3,
                volume=0,
                tick_volume=100,
                spread=0.1,
            )
        )
    write_canonical_candles_csv(
        data_path,
        candles,
        source="SYNTHETIC_AI_DRAFT",
        price_basis="BID",
    )
    data_sha = sha256(data_path)

    samples = []
    swings = []
    for wi in range(1, 7):
        source_start = (wi - 1) * 192
        sample_id = f"XAUUSD_H1_AI_DRAFT_{wi:03d}"
        samples.append(
            {
                "sample_id": sample_id,
                "window_number": wi,
                "split": "TEST",
                "source_start_index": source_start,
                "source_end_index": source_start + 191,
                "labelable_start_index": 0,
                "labelable_end_index": 191,
                "bars": 192,
                "start_timestamp": candles[source_start].timestamp.isoformat(),
                "end_timestamp": candles[source_start + 191].timestamp.isoformat(),
            }
        )
        for seq, (pivot, direction, conf, tier, scope) in enumerate(
            [
                (20, "HIGH", 25, "MAJOR", "EXTERNAL"),
                (50, "LOW", 55, "MINOR", "INTERNAL"),
            ],
            start=1,
        ):
            candle = candles[source_start + pivot]
            conf_candle = candles[source_start + conf]
            swings.append(
                {
                    "label_id": f"{sample_id}_SWG_{seq:03d}",
                    "sample_id": sample_id,
                    "pivot_index": pivot,
                    "source_bar_index": source_start + pivot,
                    "timestamp": candle.timestamp.isoformat(),
                    "price": candle.high if direction == "HIGH" else candle.low,
                    "price_field": direction,
                    "direction": direction,
                    "tier": tier,
                    "scope": scope,
                    "confirmation_status": "CONFIRMED",
                    "confirmed_at_index": conf,
                    "confirmed_at_timestamp": conf_candle.timestamp.isoformat(),
                    "confidence": 0.88,
                    "tags": ["AI_ASSISTED_ENGINEERING_DRAFT"],
                    "notes": "",
                    "annotator_id": "ASSISTANT_ENGINEERING_DRAFT",
                    "review_status": "AI_DRAFT",
                }
            )

    labels = {
        "benchmark_id": FREEZER.DATASET_ID,
        "benchmark_version": "1.0.0-ai-assisted-engineering-draft",
        "label_policy_version": FREEZER.PROTOCOL_ID,
        "label_origin": FREEZER.LABEL_ORIGIN,
        "status": FREEZER.PACKAGE_STATUS,
        "benchmark_type": FREEZER.BENCHMARK_TYPE,
        "dataset": {
            "dataset_id": FREEZER.DATASET_ID,
            "symbol": "XAUUSD",
            "timeframe": "H1",
            "timezone": "UTC",
            "price_basis": "BID",
            "source": "SYNTHETIC_AI_DRAFT",
            "data_file": data_path.name,
            "data_sha256": data_sha,
            "bar_count": len(candles),
            "first_timestamp": candles[0].timestamp.isoformat(),
            "last_timestamp": candles[-1].timestamp.isoformat(),
        },
        "samples": samples,
        "swings": swings,
        "eligibility": {
            "eligible_for_tuning": False,
            "eligible_for_human_benchmark": False,
            "eligible_for_release_gate": False,
            "eligible_for_production_certification": False,
            "eligible_for_engineering_diagnostic": True,
            "prospective_test": False,
            "human_adjudicated": False,
        },
        "review": {"warning": EVALUATOR.DIAGNOSTIC_WARNING},
        "warning": EVALUATOR.DIAGNOSTIC_WARNING,
    }
    write_json(labels_path, labels)
    labels_sha = sha256(labels_path)

    datasets = []
    for sample in samples:
        datasets.append(
            {
                "id": sample["sample_id"],
                "sample_id": sample["sample_id"],
                "symbol": "XAUUSD",
                "timeframe": "H1",
                "regime": "unknown",
                "bars": 192,
                "labels_file": labels_path.name,
                "human_review": False,
                "label_source": FREEZER.LABEL_ORIGIN,
                "evaluation_tolerance_bars": 0,
                "description": "synthetic",
                "source_type": "real",
                "data_file": data_path.name,
                "data_sha256": data_sha,
                "source_start_index": sample["source_start_index"],
                "source_end_index": sample["source_end_index"],
                "labelable_start_index": 0,
                "labelable_end_index": 191,
                "split": "TEST",
                "label_origin": FREEZER.LABEL_ORIGIN,
                "enabled": True,
            }
        )

    # Synthetic selection evidence for evaluator hash checks.
    selection_root = tmp_path / "selection_evidence"
    selection_root.mkdir()
    window_hashes = {}
    window_entries = []
    for wi in range(1, 7):
        fname = f"window_{wi:02d}.csv"
        path = selection_root / fname
        make_window_csv(path, start=start + timedelta(days=wi))
        digest = sha256(path)
        window_hashes[fname] = digest
        window_entries.append(
            {
                "window_number": wi,
                "file": fname,
                "sha256": digest,
                "bars": 192,
                "start_index": 0,
                "end_index_exclusive": 192,
            }
        )
    selection = {
        "windows": window_entries,
        "protocol_id": FREEZER.PROTOCOL_ID,
    }
    selection_path = selection_root / "selection_manifest.json"
    write_json(selection_path, selection)
    selection_sha = sha256(selection_path)

    manifest = {
        "manifest_version": "1.0",
        "dataset_id": FREEZER.DATASET_ID,
        "protocol_id": FREEZER.PROTOCOL_ID,
        "benchmark_type": FREEZER.BENCHMARK_TYPE,
        "label_origin": FREEZER.LABEL_ORIGIN,
        "status": FREEZER.PACKAGE_STATUS,
        "path_resolution": "PACKAGE_RELATIVE",
        "split": "TEST",
        "candidate": protocol["candidate"],
        "baseline": protocol["baseline"],
        "eligibility": labels["eligibility"],
        "files": {
            "data": {"path": data_path.name, "sha256": data_sha},
            "labels": {"path": labels_path.name, "sha256": labels_sha},
        },
        "datasets": datasets,
        "contamination_controls": {
            "labels_generated_by_ai": True,
            "human_blind_pass_completed": False,
            "predictions_loaded_during_label_creation": False,
            "swing_engine_executed_during_label_creation": False,
            "predictions_loaded": False,
            "swing_detector_executed": False,
            "candidate_evaluated": False,
            "baseline_evaluated": False,
        },
        "warning": EVALUATOR.DIAGNOSTIC_WARNING,
    }
    write_json(manifest_path, manifest)
    manifest_sha = sha256(manifest_path)

    receipt = {
        "dataset_id": FREEZER.DATASET_ID,
        "protocol_id": FREEZER.PROTOCOL_ID,
        "benchmark_type": FREEZER.BENCHMARK_TYPE,
        "label_origin": FREEZER.LABEL_ORIGIN,
        "status": FREEZER.PACKAGE_STATUS,
        "candidate": protocol["candidate"],
        "baseline": protocol["baseline"],
        "source_evidence": {
            "selection_manifest": {
                "path": str(selection_path),
                "sha256": selection_sha,
            },
            "windows": window_hashes,
            "protocol": {
                "path": str(protocol_path),
                "sha256": sha256(protocol_path),
            },
        },
        "outputs": {
            "data_sha256": data_sha,
            "labels_sha256": labels_sha,
            "manifest_sha256": manifest_sha,
        },
        "warning": EVALUATOR.DIAGNOSTIC_WARNING,
    }
    write_json(receipt_path, receipt)

    return {
        "package": package,
        "selection_sha": selection_sha,
        "selection_path": selection_path,
    }


# --- Freezer / schema validation ---


def test_ai_draft_schema_validation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    draft_root, selection_root = create_synthetic_draft_and_selection(tmp_path)
    patch_expected_selection(monkeypatch, selection_root)
    validated = FREEZER.validate_draft_inputs(draft_root, selection_root)
    assert validated["counts"] == {1: 4, 2: 8, 3: 4, 4: 9, 5: 6, 6: 11}
    assert validated["pass1_sha"] is None


def test_wrong_label_origin_refusal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    draft_root, selection_root = create_synthetic_draft_and_selection(tmp_path)
    patch_expected_selection(monkeypatch, selection_root)
    doc = json.loads((draft_root / "ai_assisted_labels.json").read_text())
    doc["labels"][0]["origin"] = "HUMAN_ADJUDICATED"
    write_json(draft_root / "ai_assisted_labels.json", doc)
    with pytest.raises(FREEZER.FreezeError, match="forbidden|must be exactly"):
        FREEZER.validate_draft_inputs(draft_root, selection_root)


def test_human_adjudicated_claim_refusal(tmp_path: Path):
    fixture = create_frozen_ai_package(tmp_path)
    package = fixture["package"]
    labels_path = package / EVALUATOR.LABELS_FILENAME
    labels = json.loads(labels_path.read_text())
    labels["label_origin"] = "HUMAN_ADJUDICATED"
    labels["status"] = FREEZER.AI_DRAFT_STATUS  # keep status so origin gate is hit
    write_json(labels_path, labels)
    receipt_path = package / "freeze_receipt.json"
    receipt = json.loads(receipt_path.read_text())
    receipt["outputs"]["labels_sha256"] = sha256(labels_path)
    write_json(receipt_path, receipt)
    with pytest.raises(SystemExit, match="forbidden|must be exactly|HUMAN"):
        EVALUATOR.load_package(package)


def test_ai_assisted_expert_draft_origin_refusal(tmp_path: Path):
    fixture = create_frozen_ai_package(tmp_path)
    package = fixture["package"]
    labels_path = package / EVALUATOR.LABELS_FILENAME
    labels = json.loads(labels_path.read_text())
    labels["label_origin"] = "AI_ASSISTED_EXPERT_DRAFT"
    write_json(labels_path, labels)
    receipt_path = package / "freeze_receipt.json"
    receipt = json.loads(receipt_path.read_text())
    receipt["outputs"]["labels_sha256"] = sha256(labels_path)
    write_json(receipt_path, receipt)
    with pytest.raises(SystemExit, match="forbidden|AI_ASSISTED_EXPERT_DRAFT"):
        EVALUATOR.load_package(package)


def test_unknown_origin_refusal(tmp_path: Path):
    fixture = create_frozen_ai_package(tmp_path)
    package = fixture["package"]
    labels_path = package / EVALUATOR.LABELS_FILENAME
    labels = json.loads(labels_path.read_text())
    labels["label_origin"] = "SOMETHING_ELSE"
    write_json(labels_path, labels)
    receipt_path = package / "freeze_receipt.json"
    receipt = json.loads(receipt_path.read_text())
    receipt["outputs"]["labels_sha256"] = sha256(labels_path)
    write_json(receipt_path, receipt)
    with pytest.raises(SystemExit, match="must be exactly"):
        EVALUATOR.load_package(package)


def test_human_benchmark_eligibility_refusal(tmp_path: Path):
    fixture = create_frozen_ai_package(tmp_path)
    package = fixture["package"]
    manifest_path = package / EVALUATOR.MANIFEST_FILENAME
    manifest = json.loads(manifest_path.read_text())
    manifest["eligibility"]["eligible_for_human_benchmark"] = True
    write_json(manifest_path, manifest)
    receipt_path = package / "freeze_receipt.json"
    receipt = json.loads(receipt_path.read_text())
    receipt["outputs"]["manifest_sha256"] = sha256(manifest_path)
    write_json(receipt_path, receipt)
    with pytest.raises(SystemExit, match="eligible_for_human_benchmark"):
        EVALUATOR.load_package(package)


def test_human_adjudication_flag_refusal(tmp_path: Path):
    fixture = create_frozen_ai_package(tmp_path)
    package = fixture["package"]
    labels_path = package / EVALUATOR.LABELS_FILENAME
    labels = json.loads(labels_path.read_text())
    labels["eligibility"]["human_adjudicated"] = True
    write_json(labels_path, labels)
    receipt_path = package / "freeze_receipt.json"
    receipt = json.loads(receipt_path.read_text())
    receipt["outputs"]["labels_sha256"] = sha256(labels_path)
    write_json(receipt_path, receipt)
    with pytest.raises(SystemExit, match="human_adjudicated"):
        EVALUATOR.load_package(package)


def test_release_and_production_eligibility_refusal(tmp_path: Path):
    fixture = create_frozen_ai_package(tmp_path)
    package = fixture["package"]
    manifest_path = package / EVALUATOR.MANIFEST_FILENAME
    manifest = json.loads(manifest_path.read_text())
    manifest["eligibility"]["eligible_for_release_gate"] = True
    write_json(manifest_path, manifest)
    receipt_path = package / "freeze_receipt.json"
    receipt = json.loads(receipt_path.read_text())
    receipt["outputs"]["manifest_sha256"] = sha256(manifest_path)
    write_json(receipt_path, receipt)
    with pytest.raises(SystemExit, match="eligible_for_release_gate"):
        EVALUATOR.load_package(package)

    manifest["eligibility"]["eligible_for_release_gate"] = False
    manifest["eligibility"]["eligible_for_production_certification"] = True
    write_json(manifest_path, manifest)
    receipt["outputs"]["manifest_sha256"] = sha256(manifest_path)
    write_json(receipt_path, receipt)
    with pytest.raises(SystemExit, match="eligible_for_production_certification"):
        EVALUATOR.load_package(package)


def test_source_timestamp_mismatch_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    draft_root, selection_root = create_synthetic_draft_and_selection(tmp_path)
    patch_expected_selection(monkeypatch, selection_root)
    doc = json.loads((draft_root / "ai_assisted_labels.json").read_text())
    doc["labels"][0]["timestamp_utc"] = "2099-01-01T00:00:00Z"
    write_json(draft_root / "ai_assisted_labels.json", doc)
    with pytest.raises(FREEZER.FreezeError, match="timestamp mismatch"):
        FREEZER.validate_draft_inputs(draft_root, selection_root)


def test_source_price_mismatch_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    draft_root, selection_root = create_synthetic_draft_and_selection(tmp_path)
    patch_expected_selection(monkeypatch, selection_root)
    doc = json.loads((draft_root / "ai_assisted_labels.json").read_text())
    doc["labels"][0]["price"] = "1.0000000000"
    write_json(draft_root / "ai_assisted_labels.json", doc)
    with pytest.raises(FREEZER.FreezeError, match="price mismatch"):
        FREEZER.validate_draft_inputs(draft_root, selection_root)


def test_direction_alternation_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    draft_root, selection_root = create_synthetic_draft_and_selection(tmp_path)
    patch_expected_selection(monkeypatch, selection_root)
    doc = json.loads((draft_root / "ai_assisted_labels.json").read_text())
    # Force two HIGHs in window 1.
    for lab in doc["labels"]:
        if lab["window_number"] == 1 and lab["direction"] == "LOW":
            lab["direction"] = "HIGH"
            lab["price_field"] = "high"
            # Fix price to candle high for that pivot.
            rows = list(
                csv.DictReader(
                    (selection_root / "window_01_0_192.csv").open(encoding="utf-8")
                )
            )
            lab["price"] = rows[lab["pivot_index"]]["high"]
            break
    write_json(draft_root / "ai_assisted_labels.json", doc)
    with pytest.raises(FREEZER.FreezeError, match="alternate"):
        FREEZER.validate_draft_inputs(draft_root, selection_root)


def test_confirmation_order_refusal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    draft_root, selection_root = create_synthetic_draft_and_selection(tmp_path)
    patch_expected_selection(monkeypatch, selection_root)
    doc = json.loads((draft_root / "ai_assisted_labels.json").read_text())
    doc["labels"][0]["confirmed_at_index"] = doc["labels"][0]["pivot_index"]
    write_json(draft_root / "ai_assisted_labels.json", doc)
    with pytest.raises(FREEZER.FreezeError, match="confirmation order"):
        FREEZER.validate_draft_inputs(draft_root, selection_root)


def test_duplicate_label_id_refusal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    draft_root, selection_root = create_synthetic_draft_and_selection(tmp_path)
    patch_expected_selection(monkeypatch, selection_root)
    doc = json.loads((draft_root / "ai_assisted_labels.json").read_text())
    doc["labels"][1]["label_id"] = doc["labels"][0]["label_id"]
    write_json(draft_root / "ai_assisted_labels.json", doc)
    with pytest.raises(FREEZER.FreezeError, match="duplicate label_id"):
        FREEZER.validate_draft_inputs(draft_root, selection_root)


def test_window_hash_tampering_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    draft_root, selection_root = create_synthetic_draft_and_selection(tmp_path)
    patch_expected_selection(monkeypatch, selection_root)
    path = selection_root / "window_01_0_192.csv"
    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(FREEZER.FreezeError, match="hash mismatch"):
        FREEZER.validate_draft_inputs(draft_root, selection_root)


def test_selection_manifest_tampering_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    draft_root, selection_root = create_synthetic_draft_and_selection(tmp_path)
    # Keep expected hash as original, then tamper.
    patch_expected_selection(monkeypatch, selection_root)
    original = FREEZER.EXPECTED_SELECTION_SHA
    manifest = selection_root / "selection_manifest.json"
    data = json.loads(manifest.read_text())
    data["tampered"] = True
    write_json(manifest, data)
    monkeypatch.setattr(FREEZER, "EXPECTED_SELECTION_SHA", original)
    with pytest.raises(FREEZER.FreezeError, match="selection manifest SHA-256"):
        FREEZER.validate_draft_inputs(draft_root, selection_root)


def test_deterministic_canonical_gzip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    draft_root, selection_root = create_synthetic_draft_and_selection(tmp_path)
    patch_expected_selection(monkeypatch, selection_root)

    out1 = tmp_path / "pkg1"
    out2 = tmp_path / "pkg2"
    frozen_at = "2026-07-21T12:00:00Z"

    def run(output: Path) -> str:
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "freeze",
                "--draft-root",
                str(draft_root),
                "--selection-root",
                str(selection_root),
                "--output-root",
                str(output),
                "--frozen-at",
                frozen_at,
            ],
        )
        assert FREEZER.main() == 0
        return sha256(output / FREEZER.DATA_FILENAME)

    h1 = run(out1)
    h2 = run(out2)
    assert h1 == h2


def test_immutable_package_refusal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    draft_root, selection_root = create_synthetic_draft_and_selection(tmp_path)
    patch_expected_selection(monkeypatch, selection_root)
    output = tmp_path / "pkg"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "freeze",
            "--draft-root",
            str(draft_root),
            "--selection-root",
            str(selection_root),
            "--output-root",
            str(output),
            "--frozen-at",
            "2026-07-21T12:00:00Z",
        ],
    )
    assert FREEZER.main() == 0
    with pytest.raises(FREEZER.FreezeError, match="already exists"):
        FREEZER.main()


# --- Evaluator ---


def test_package_checksum_tampering_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    fixture = create_frozen_ai_package(tmp_path)
    package = fixture["package"]
    monkeypatch.setattr(
        EVALUATOR, "EXPECTED_SELECTION_SHA", fixture["selection_sha"]
    )
    receipt_path = package / "freeze_receipt.json"
    receipt = json.loads(receipt_path.read_text())
    receipt["outputs"]["data_sha256"] = "0" * 64
    write_json(receipt_path, receipt)
    with pytest.raises(SystemExit, match="checksum mismatch"):
        EVALUATOR.load_package(package)


def test_missing_evaluator_tag_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    fixture = create_frozen_ai_package(tmp_path)
    monkeypatch.setattr(
        EVALUATOR, "EXPECTED_SELECTION_SHA", fixture["selection_sha"]
    )

    def fake_post_verify(commit: str) -> dict:
        return {"candidate_tag_commit": commit}

    def fake_git_output(*args: str) -> str:
        if args and args[0] == "rev-parse":
            raise subprocess.CalledProcessError(1, args)
        return ""

    monkeypatch.setattr(EVALUATOR.POST, "verify_repository", fake_post_verify)
    monkeypatch.setattr(EVALUATOR.POST, "git_output", fake_git_output)
    with pytest.raises(SystemExit, match="freeze tag is missing"):
        EVALUATOR.verify_repository(CANDIDATE_COMMIT)


def test_evaluator_file_modification_after_tag_refusal(
    monkeypatch: pytest.MonkeyPatch,
):
    def fake_post_verify(commit: str) -> dict:
        return {"candidate_tag_commit": commit}

    def fake_git_output(*args: str) -> str:
        if args and args[0] == "rev-parse":
            return "abc123"
        if args and args[0] == "diff":
            return EVALUATOR.AI_DRAFT_EVALUATOR_SCRIPT
        return ""

    monkeypatch.setattr(EVALUATOR.POST, "verify_repository", fake_post_verify)
    monkeypatch.setattr(EVALUATOR.POST, "git_output", fake_git_output)
    with pytest.raises(SystemExit, match="changed after its freeze tag"):
        EVALUATOR.verify_repository(CANDIDATE_COMMIT)


def test_later_data_only_commits_allowed(monkeypatch: pytest.MonkeyPatch):
    def fake_post_verify(commit: str) -> dict:
        return {"candidate_tag_commit": commit}

    def fake_git_output(*args: str) -> str:
        if args and args[0] == "rev-parse":
            return "abc123"
        if args and args[0] == "diff":
            return ""  # evaluator script unchanged
        return ""

    monkeypatch.setattr(EVALUATOR.POST, "verify_repository", fake_post_verify)
    monkeypatch.setattr(EVALUATOR.POST, "git_output", fake_git_output)
    evidence = EVALUATOR.verify_repository(CANDIDATE_COMMIT)
    assert evidence["ai_draft_evaluator_tag"] == EVALUATOR.AI_DRAFT_EVALUATOR_TAG


def test_unblinding_receipt_survives_synthetic_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    fixture = create_frozen_ai_package(tmp_path)
    package = fixture["package"]
    monkeypatch.setattr(
        EVALUATOR, "EXPECTED_SELECTION_SHA", fixture["selection_sha"]
    )
    output = tmp_path / "eval-out"

    monkeypatch.setattr(
        EVALUATOR,
        "verify_repository",
        lambda commit: {"ok": True, "candidate_tag_commit": commit},
    )
    monkeypatch.setattr(
        EVALUATOR,
        "load_samples",
        lambda specs, manifest_path: {spec.id: ([], []) for spec in specs},
    )

    def boom(*args, **kwargs):
        raise RuntimeError("synthetic detection failure")

    monkeypatch.setattr(EVALUATOR, "run_profile", boom)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "evaluate",
            "--package-root",
            str(package),
            "--output-root",
            str(output),
        ],
    )
    with pytest.raises(RuntimeError, match="synthetic detection failure"):
        EVALUATOR.main()
    unblinding = json.loads((output / EVALUATOR.UNBLINDING_NAME).read_text())
    assert unblinding["state"] == "UNBLINDING_STARTED"
    assert EVALUATOR.DIAGNOSTIC_WARNING in unblinding["warning"]


def test_real_evaluator_rerun_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    fixture = create_frozen_ai_package(tmp_path)
    package = fixture["package"]
    monkeypatch.setattr(
        EVALUATOR, "EXPECTED_SELECTION_SHA", fixture["selection_sha"]
    )
    output = tmp_path / "eval-out"
    output.mkdir()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "evaluate",
            "--package-root",
            str(package),
            "--output-root",
            str(output),
        ],
    )
    with pytest.raises(SystemExit, match="already exists"):
        EVALUATOR.main()


def test_forbidden_promotion_values_impossible():
    for value in EVALUATOR.FORBIDDEN_DECISIONS:
        assert value not in EVALUATOR.ALLOWED_DECISIONS
    for value in (
        "PROMOTE_V2_3_0_FINAL",
        "PASS_RETROSPECTIVE_ENGINEERING_GATE",
        "FAIL_RETROSPECTIVE_ENGINEERING_GATE",
        "PRODUCTION_READY",
        "RELEASE_APPROVED",
    ):
        assert value in EVALUATOR.FORBIDDEN_DECISIONS


def test_candidate_better_conclusion():
    assert (
        EVALUATOR.diagnostic_conclusion(
            candidate=aggregate(0.9, 0.8),
            baseline=aggregate(0.8, 0.7),
            prefix={"summary": {"failures": 0}},
        )
        == "CANDIDATE_OUTPERFORMS_BASELINE_ON_AI_DRAFT"
    )


def test_baseline_better_conclusion():
    assert (
        EVALUATOR.diagnostic_conclusion(
            candidate=aggregate(0.7, 0.6),
            baseline=aggregate(0.8, 0.7),
            prefix={"summary": {"failures": 0}},
        )
        == "BASELINE_OUTPERFORMS_CANDIDATE_ON_AI_DRAFT"
    )


def test_mixed_result_conclusion():
    assert (
        EVALUATOR.diagnostic_conclusion(
            candidate=aggregate(0.9, 0.6),
            baseline=aggregate(0.8, 0.7),
            prefix={"summary": {"failures": 0}},
        )
        == "MIXED_AI_DRAFT_RESULT"
    )


def test_prefix_failure_inconclusive():
    assert (
        EVALUATOR.diagnostic_conclusion(
            candidate=aggregate(0.9, 0.8),
            baseline=aggregate(0.1, 0.1),
            prefix={"summary": {"failures": 2}},
        )
        == "AI_DRAFT_DIAGNOSTIC_INCONCLUSIVE"
    )


def test_repository_does_not_require_pass_1_json():
    """Abandoned blind template must not be a repository test dependency."""
    assert not PASS1_REPO_PATH.exists()


def test_freezer_historical_pass_template_sha_constant():
    assert FREEZER.EXPECTED_PASS1_SHA == EXPECTED_PASS1
    assert EXPECTED_PASS1 == (
        "d1fe3440c0cc21eb888a07caadeb6893830c0354b7341b8157a64debca1bd0ca"
    )


def test_committed_ai_draft_receipt_records_historical_pass_template_sha():
    """Frozen package receipt preserves the known empty-template SHA evidence."""
    receipt_path = FROZEN_AI_PACKAGE / "freeze_receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    pass1_evidence = receipt["source_evidence"]["pass_1_json"]
    assert pass1_evidence["sha256"] == EXPECTED_PASS1
    assert pass1_evidence["sha256"] == FREEZER.EXPECTED_PASS1_SHA
    assert pass1_evidence["path"].endswith("labels/pass_1.json")
    assert pass1_evidence["unchanged"] is True


def test_ai_draft_freezer_runs_without_repository_pass_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    assert not PASS1_REPO_PATH.exists()
    draft_root, selection_root = create_synthetic_draft_and_selection(tmp_path)
    patch_expected_selection(monkeypatch, selection_root)
    validated = FREEZER.validate_draft_inputs(draft_root, selection_root)
    assert validated["pass1_sha"] is None
    assert validated["pass1_present_in_repository"] is False


def test_freezer_receipt_metadata_when_pass_template_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Future receipts retain historical SHA while marking repository absence."""
    assert not PASS1_REPO_PATH.exists()
    draft_root, selection_root = create_synthetic_draft_and_selection(tmp_path)
    patch_expected_selection(monkeypatch, selection_root)
    output = tmp_path / "pkg_absent_pass"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "freeze",
            "--draft-root",
            str(draft_root),
            "--selection-root",
            str(selection_root),
            "--output-root",
            str(output),
            "--frozen-at",
            "2026-07-21T12:00:00Z",
        ],
    )
    assert FREEZER.main() == 0
    receipt = json.loads(
        (output / "freeze_receipt.json").read_text(encoding="utf-8")
    )
    pass1_meta = receipt["source_evidence"]["pass_1_json"]
    assert pass1_meta["sha256"] is None
    assert pass1_meta["present_in_repository"] is False
    assert pass1_meta["historical_empty_template_sha256"] == EXPECTED_PASS1
    assert pass1_meta["historical_empty_template_sha256"] == (
        FREEZER.EXPECTED_PASS1_SHA
    )


def test_freezer_accepts_synthetic_pass_template_under_tmp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Optional-present path: synthetic tmp file + monkeypatched expected SHA."""
    draft_root, selection_root = create_synthetic_draft_and_selection(tmp_path)
    patch_expected_selection(monkeypatch, selection_root)
    synthetic = tmp_path / "synthetic_pass_1.json"
    write_json(
        synthetic,
        {
            "schema_version": "SYNTHETIC_PASS_TEMPLATE_V1",
            "status": "DRAFT",
            "labels": [],
        },
    )
    digest = sha256(synthetic)
    monkeypatch.setattr(FREEZER, "PASS1_PATH", synthetic)
    monkeypatch.setattr(FREEZER, "EXPECTED_PASS1_SHA", digest)
    validated = FREEZER.validate_draft_inputs(draft_root, selection_root)
    assert validated["pass1_present_in_repository"] is True
    assert validated["pass1_sha"] == digest
    assert not PASS1_REPO_PATH.exists()


def test_frozen_selection_and_windows_remain_byte_identical():
    assert sha256(SELECTION) == EXPECTED_SELECTION
    for name, digest in EXPECTED_WINDOWS.items():
        assert sha256(WINDOWS_ROOT / name) == digest


def test_decimal_price_match_helper():
    assert Decimal("1894.8900000000") == Decimal("1894.8900000000")


def test_annotations_py_matches_head():
    """AI draft must not modify global annotation policy."""
    result = subprocess.run(
        ["git", "diff", "--", "swing_engine/annotations.py"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout == ""
    text = (ROOT / "swing_engine/annotations.py").read_text(encoding="utf-8")
    assert "AI_ASSISTED_ENGINEERING_DRAFT" not in text
    assert 'PROTECTED_ANNOTATION_ORIGINS = HUMAN_ORIGINS | {"AI_ASSISTED_EXPERT_DRAFT"}' in text


def test_exact_ai_origin_accepted_locally(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    draft_root, selection_root = create_synthetic_draft_and_selection(tmp_path)
    patch_expected_selection(monkeypatch, selection_root)
    validated = FREEZER.validate_draft_inputs(draft_root, selection_root)
    assert validated["labels_doc"]["origin"] == FREEZER.AI_DRAFT_ORIGIN
    assert FREEZER.refuse_non_ai_draft_origin(
        FREEZER.AI_DRAFT_ORIGIN, field="origin"
    ) == FREEZER.AI_DRAFT_ORIGIN


def test_evaluator_accepts_unchanged_frozen_package():
    package = (
        ROOT
        / "benchmarks/data/engineering/XAUUSD/H1_2022_2024_ai_draft_v1"
    )
    assert package.exists()
    loaded = EVALUATOR.load_package(package)
    assert loaded["hashes"] == EVALUATOR.EXPECTED_PACKAGE_OUTPUTS
    assert sha256(package / "freeze_receipt.json") == (
        EVALUATOR.EXPECTED_FREEZE_RECEIPT_SHA
    )
    assert loaded["labels"]["label_origin"] == EVALUATOR.AI_DRAFT_ORIGIN
    assert len(loaded["labels"]["swings"]) == 42
    assert len(loaded["specs"]) == 6


def test_local_validation_does_not_use_protected_origins():
    import swing_engine.annotations as annotations

    assert FREEZER.AI_DRAFT_ORIGIN not in annotations.PROTECTED_ANNOTATION_ORIGINS
    assert EVALUATOR.AI_DRAFT_ORIGIN not in annotations.PROTECTED_ANNOTATION_ORIGINS

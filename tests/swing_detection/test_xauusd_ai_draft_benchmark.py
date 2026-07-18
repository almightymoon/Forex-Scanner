import json
from pathlib import Path

from swing_engine.annotations import validate_annotation_document


REPO_ROOT = Path(__file__).resolve().parents[2]
LABELS_PATH = REPO_ROOT / "benchmarks" / "labels" / "XAUUSD_H1.human.json"


def test_xauusd_ai_assisted_draft_is_internally_consistent():
    document = json.loads(LABELS_PATH.read_text(encoding="utf-8"))

    assert document["label_origin"] == "AI_ASSISTED_EXPERT_DRAFT"
    assert document["status"] == "READY_FOR_HUMAN_ADJUDICATION"
    assert len(document["samples"]) == 12
    assert len(document["swings"]) == 171
    assert not [
        issue
        for issue in validate_annotation_document(LABELS_PATH)
        if issue.severity == "ERROR"
    ]


def test_each_xauusd_sample_has_alternating_confirmed_structure():
    document = json.loads(LABELS_PATH.read_text(encoding="utf-8"))

    for sample in document["samples"]:
        labels = sorted(
            (
                item
                for item in document["swings"]
                if item["sample_id"] == sample["sample_id"]
            ),
            key=lambda item: item["pivot_index"],
        )
        assert len(labels) >= 10
        assert all(item["confirmed_at_index"] > item["pivot_index"] for item in labels)
        assert all(
            left["direction"] != right["direction"]
            for left, right in zip(labels, labels[1:])
        )

def test_xauusd_calibration_uses_a_chronological_train_validation_holdout():
    document = json.loads(LABELS_PATH.read_text(encoding="utf-8"))

    samples = document["samples"]
    assert [sample["split"] for sample in samples[:8]] == ["TRAIN"] * 8
    assert [sample["split"] for sample in samples[8:]] == ["VALIDATION"] * 4
    assert not [sample for sample in samples if sample["split"] == "TEST"]

    split_policy = document["split_policy"]
    assert split_policy["method"] == "chronological_non_overlapping_holdout"
    assert split_policy["train_samples"] == [
        f"XAUUSD_H1_{index:03d}" for index in range(1, 9)
    ]
    assert split_policy["validation_samples"] == [
        f"XAUUSD_H1_{index:03d}" for index in range(9, 13)
    ]

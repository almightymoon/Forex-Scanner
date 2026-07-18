#!/usr/bin/env python3
"""Freeze the blind AI-assisted XAUUSD H1 2026H1 TEST labels.

This script uses only:
- the previously rendered blind raw-candle charts;
- the raw-candle candidate aid;
- the frozen candle records.

No swing-engine predictions are loaded or generated.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Final


ROOT: Final = Path(__file__).resolve().parents[1]

BARS_PATH: Final = (
    ROOT
    / "benchmarks"
    / "reports"
    / "XAUUSD_H1_2026H1_test_windows_bars.json"
)

LABELS_PATH: Final = (
    ROOT
    / "benchmarks"
    / "labels"
    / "XAUUSD_H1_2026H1.human.json"
)

RECEIPT_PATH: Final = (
    ROOT
    / "benchmarks"
    / "reports"
    / "XAUUSD_H1_2026H1_labels_freeze_receipt.json"
)

DATASET_ID: Final = "XAUUSD_H1_2026H1_LOCKED_TEST_V1"

# Each tuple:
# (pivot_index, direction, confirmed_at_index, tier, scope)
#
# These decisions were made from blind raw-candle charts before viewing or
# running any v2.2 predictions.
DECISIONS: Final = {
    "XAUUSD_H1_2026H1_001": [
        (53, "HIGH", 55, "MINOR", "INTERNAL"),
        (69, "LOW", 74, "MINOR", "INTERNAL"),
        (80, "HIGH", 100, "MINOR", "INTERNAL"),
        (102, "LOW", 103, "MAJOR", "EXTERNAL"),
        (160, "HIGH", 161, "MAJOR", "EXTERNAL"),
        (173, "LOW", 174, "MAJOR", "EXTERNAL"),
        (201, "HIGH", 208, "MINOR", "INTERNAL"),
        (209, "LOW", 212, "MINOR", "INTERNAL"),
        (229, "HIGH", 236, "MAJOR", "EXTERNAL"),
        (244, "LOW", 245, "MAJOR", "EXTERNAL"),
    ],
    "XAUUSD_H1_2026H1_002": [
        (46, "LOW", 47, "MAJOR", "EXTERNAL"),
        (68, "HIGH", 70, "MAJOR", "EXTERNAL"),
        (71, "LOW", 75, "MINOR", "INTERNAL"),
        (89, "HIGH", 91, "MAJOR", "EXTERNAL"),
        (91, "LOW", 94, "MINOR", "INTERNAL"),
        (127, "HIGH", 128, "MAJOR", "EXTERNAL"),
        (154, "LOW", 155, "MAJOR", "EXTERNAL"),
        (183, "HIGH", 187, "MAJOR", "EXTERNAL"),
        (219, "LOW", 223, "MAJOR", "EXTERNAL"),
        (244, "HIGH", 247, "MAJOR", "EXTERNAL"),
        (251, "LOW", 257, "MINOR", "INTERNAL"),
        (259, "HIGH", 261, "MINOR", "INTERNAL"),
    ],
    "XAUUSD_H1_2026H1_003": [
        (46, "HIGH", 47, "MINOR", "INTERNAL"),
        (49, "LOW", 53, "MAJOR", "EXTERNAL"),
        (86, "HIGH", 89, "MAJOR", "EXTERNAL"),
        (107, "LOW", 108, "MINOR", "INTERNAL"),
        (127, "HIGH", 130, "MAJOR", "EXTERNAL"),
        (137, "LOW", 139, "MAJOR", "EXTERNAL"),
        (152, "HIGH", 154, "MAJOR", "EXTERNAL"),
        (162, "LOW", 163, "MAJOR", "EXTERNAL"),
        (177, "HIGH", 178, "MAJOR", "EXTERNAL"),
        (201, "LOW", 210, "MINOR", "INTERNAL"),
        (215, "HIGH", 217, "MAJOR", "EXTERNAL"),
        (222, "LOW", 223, "MAJOR", "EXTERNAL"),
        (227, "HIGH", 229, "MINOR", "INTERNAL"),
        (245, "LOW", 246, "MAJOR", "EXTERNAL"),
        (258, "HIGH", 265, "MAJOR", "EXTERNAL"),
    ],
    "XAUUSD_H1_2026H1_004": [
        (43, "HIGH", 48, "MAJOR", "EXTERNAL"),
        (71, "LOW", 72, "MAJOR", "EXTERNAL"),
        (119, "HIGH", 120, "MAJOR", "EXTERNAL"),
        (127, "LOW", 131, "MINOR", "INTERNAL"),
        (146, "HIGH", 151, "MAJOR", "INTERNAL"),
        (155, "LOW", 156, "MAJOR", "INTERNAL"),
        (177, "HIGH", 184, "MAJOR", "EXTERNAL"),
        (186, "LOW", 188, "MAJOR", "EXTERNAL"),
        (208, "HIGH", 213, "MAJOR", "EXTERNAL"),
        (229, "LOW", 231, "MAJOR", "EXTERNAL"),
        (240, "HIGH", 247, "MAJOR", "EXTERNAL"),
        (249, "LOW", 256, "MINOR", "INTERNAL"),
        (256, "HIGH", 258, "MINOR", "INTERNAL"),
    ],
    "XAUUSD_H1_2026H1_005": [
        (45, "HIGH", 46, "MAJOR", "EXTERNAL"),
        (57, "LOW", 61, "MAJOR", "EXTERNAL"),
        (61, "HIGH", 69, "MINOR", "INTERNAL"),
        (81, "LOW", 83, "MAJOR", "EXTERNAL"),
        (112, "HIGH", 113, "MAJOR", "EXTERNAL"),
        (131, "LOW", 134, "MAJOR", "INTERNAL"),
        (134, "HIGH", 138, "MAJOR", "INTERNAL"),
        (149, "LOW", 150, "MAJOR", "EXTERNAL"),
        (157, "HIGH", 160, "MINOR", "INTERNAL"),
        (163, "LOW", 169, "MAJOR", "EXTERNAL"),
        (197, "HIGH", 199, "MAJOR", "EXTERNAL"),
        (219, "LOW", 222, "MAJOR", "EXTERNAL"),
        (235, "HIGH", 241, "MAJOR", "EXTERNAL"),
        (250, "LOW", 251, "MAJOR", "EXTERNAL"),
        (251, "HIGH", 252, "MINOR", "INTERNAL"),
    ],
    "XAUUSD_H1_2026H1_006": [
        (42, "LOW", 43, "MAJOR", "EXTERNAL"),
        (65, "HIGH", 68, "MAJOR", "EXTERNAL"),
        (72, "LOW", 82, "MINOR", "INTERNAL"),
        (114, "HIGH", 115, "MAJOR", "EXTERNAL"),
        (116, "LOW", 119, "MAJOR", "EXTERNAL"),
        (122, "HIGH", 129, "MAJOR", "INTERNAL"),
        (148, "LOW", 150, "MAJOR", "EXTERNAL"),
        (174, "HIGH", 178, "MAJOR", "EXTERNAL"),
        (194, "LOW", 196, "MAJOR", "EXTERNAL"),
        (200, "HIGH", 207, "MAJOR", "INTERNAL"),
        (212, "LOW", 215, "MAJOR", "EXTERNAL"),
        (215, "HIGH", 219, "MINOR", "INTERNAL"),
        (227, "LOW", 245, "MAJOR", "EXTERNAL"),
        (250, "HIGH", 257, "MAJOR", "EXTERNAL"),
        (257, "LOW", 261, "MINOR", "INTERNAL"),
    ],
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def score_label(
    tier: str,
    scope: str,
    confirmation_delay: int,
) -> tuple[int, float, float]:
    if tier == "MAJOR" and scope == "EXTERNAL":
        strength = 4
        quality = 85.0
        confidence = 0.88
    elif tier == "MAJOR":
        strength = 4
        quality = 82.0
        confidence = 0.85
    else:
        strength = 3
        quality = 78.0
        confidence = 0.82

    if confirmation_delay <= 3:
        quality += 2.0
        confidence += 0.02
    elif confirmation_delay >= 12:
        quality -= 5.0
        confidence -= 0.05

    return (
        strength,
        max(0.0, min(100.0, quality)),
        max(0.0, min(1.0, confidence)),
    )


def main() -> int:
    bars_document = json.loads(
        BARS_PATH.read_text(encoding="utf-8")
    )
    labels_document = json.loads(
        LABELS_PATH.read_text(encoding="utf-8")
    )

    if bars_document.get("dataset_id") != DATASET_ID:
        raise SystemExit(
            "Raw-window JSON has the wrong dataset ID"
        )

    if labels_document.get("benchmark_id") != DATASET_ID:
        raise SystemExit(
            "Label document has the wrong benchmark ID"
        )

    samples = {
        sample["sample_id"]: sample
        for sample in labels_document["samples"]
    }
    raw_samples = {
        sample["id"]: sample
        for sample in bars_document["samples"]
    }

    if set(DECISIONS) != set(samples):
        raise SystemExit(
            "Decision sample IDs do not match label samples"
        )

    if any(sample.get("split") != "TEST" for sample in samples.values()):
        raise SystemExit("Every locked sample must be TEST")

    swings = []

    for sample_id, decisions in DECISIONS.items():
        sample = samples[sample_id]
        raw_sample = raw_samples[sample_id]

        bars = {
            int(bar["sample_index"]): bar
            for bar in raw_sample["window_bars"]
        }

        label_start = int(sample["labelable_start_index"])
        label_end = int(sample["labelable_end_index"])
        regime = str(sample["primary_regime"])

        previous_direction = None

        for number, (
            pivot_index,
            direction,
            confirmed_at_index,
            tier,
            scope,
        ) in enumerate(decisions, start=1):
            if previous_direction == direction:
                raise SystemExit(
                    f"{sample_id}: consecutive {direction} labels"
                )
            previous_direction = direction

            if not label_start <= pivot_index <= label_end:
                raise SystemExit(
                    f"{sample_id}: pivot {pivot_index} is not labelable"
                )

            if confirmed_at_index <= pivot_index:
                raise SystemExit(
                    f"{sample_id}: invalid confirmation order"
                )

            pivot_bar = bars[pivot_index]
            confirmation_bar = bars[confirmed_at_index]

            price_field = direction
            price = float(
                pivot_bar["high"]
                if direction == "HIGH"
                else pivot_bar["low"]
            )

            delay = confirmed_at_index - pivot_index
            strength, quality, confidence = score_label(
                tier,
                scope,
                delay,
            )

            tags = [
                regime,
                "CAUSAL_CONFIRMATION",
                "AI_ASSISTED_BLIND_REVIEW",
                (
                    "MAJOR_SWING"
                    if tier == "MAJOR"
                    else "MINOR_SWING"
                ),
                (
                    "EXTERNAL_STRUCTURE"
                    if scope == "EXTERNAL"
                    else "INTERNAL_STRUCTURE"
                ),
                "DISPLACEMENT_CONFIRMED",
            ]

            if delay <= 3:
                tags.append("FAST_CONFIRMATION")
            elif delay >= 12:
                tags.append("SLOW_CONFIRMATION")

            type_description = (
                f"{tier.lower()} {scope.lower()} "
                f"swing {direction.lower()}"
            )

            swings.append({
                "label_id": (
                    f"{sample_id}_SWG_{number:03d}"
                ),
                "sample_id": sample_id,
                "pivot_index": pivot_index,
                "source_bar_index": int(
                    pivot_bar["source_index"]
                ),
                "timestamp": pivot_bar["timestamp"],
                "price": price,
                "price_field": price_field,
                "direction": direction,
                "tier": tier,
                "scope": scope,
                "confirmation_status": "CONFIRMED",
                "confirmed_at_index": confirmed_at_index,
                "confirmed_at_timestamp": (
                    confirmation_bar["timestamp"]
                ),
                "strength": strength,
                "quality_score": quality,
                "confidence": confidence,
                "tags": tags,
                "notes": (
                    "Blind AI-assisted expert draft from raw "
                    f"XAUUSD H1 candles. {type_description.capitalize()} "
                    f"confirmed {delay} bar(s) after the pivot. "
                    "No v2.2 predictions were viewed during labeling."
                ),
                "annotator_id": (
                    "OPENAI_BLIND_CHART_REVIEW_2026H1"
                ),
                "review_status": "AI_DRAFT",
            })

    labels_document["benchmark_version"] = (
        "1.0.0-locked-ai-draft"
    )
    labels_document["label_origin"] = (
        "AI_ASSISTED_EXPERT_DRAFT"
    )
    labels_document["status"] = "FROZEN_AI_DRAFT"
    labels_document["dataset_id"] = DATASET_ID
    labels_document["dataset"]["dataset_id"] = DATASET_ID
    labels_document["swings"] = swings

    review = labels_document.setdefault("review", {})
    review["adjudicator"] = None
    review["adjudicated_at"] = None
    review["label_frozen_at"] = datetime.now(
        timezone.utc
    ).isoformat(timespec="seconds")
    review["prediction_visibility"] = (
        "HIDDEN_DURING_LABELING"
    )
    review["notes"] = (
        "Blind AI-assisted expert draft produced from raw-candle "
        "charts and a raw-candle-only pivot aid. No v2.2 "
        "predictions were viewed. Independent human review and "
        "adjudication remain required before production certification."
    )

    LABELS_PATH.write_text(
        json.dumps(labels_document, indent=2) + "\n",
        encoding="utf-8",
    )

    counts = {
        sample_id: sum(
            1
            for swing in swings
            if swing["sample_id"] == sample_id
        )
        for sample_id in DECISIONS
    }

    receipt = {
        "dataset_id": DATASET_ID,
        "frozen_at": review["label_frozen_at"],
        "label_policy_version": labels_document[
            "label_policy_version"
        ],
        "label_origin": labels_document["label_origin"],
        "status": labels_document["status"],
        "prediction_visibility": (
            review["prediction_visibility"]
        ),
        "total_labels": len(swings),
        "labels_by_sample": counts,
        "data_sha256": labels_document["dataset"][
            "data_sha256"
        ],
        "labels_sha256": sha256(LABELS_PATH),
        "bars_helper_sha256": sha256(BARS_PATH),
        "requires_human_adjudication": True,
    }

    RECEIPT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    RECEIPT_PATH.write_text(
        json.dumps(receipt, indent=2) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(receipt, indent=2))
    print(f"Labels: {LABELS_PATH}")
    print(f"Receipt: {RECEIPT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

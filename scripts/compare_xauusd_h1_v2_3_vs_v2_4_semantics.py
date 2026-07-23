#!/usr/bin/env python3
"""Assemble refused v2.4 three-way TRAIN comparison from v2.3 overrides.

DEVELOPMENT_ONLY / TRAIN_001_008_ONLY / NOT_A_RELEASE_DECISION.

No active 2.4.0 profile. Threshold-only uses engine 2.3.0 with
hierarchy_reversal_atr=4.25. Structural refinements are reported from the
close-break audit (Rules A–C) and remain refused.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from swing_engine import LATEST_VERSION  # noqa: E402
from swing_engine.datasets import load_manifest  # noqa: E402
from swing_engine.models import SwingScope, SwingTier  # noqa: E402
from swing_engine.versions import SUPPORTED_VERSIONS  # noqa: E402


MANIFEST = ROOT / "benchmarks/datasets/XAUUSD_H1.human.manifest.json"
OUTPUT = (
    ROOT / "benchmarks/reports/XAUUSD_H1_v2_4_three_way_semantic_comparison.json"
)
CLOSE_BREAK = ROOT / "benchmarks/reports/XAUUSD_H1_v2_4_close_break_audit.json"
TRAIN_IDS = tuple(f"XAUUSD_H1_{n:03d}" for n in range(1, 9))
V23 = "2.3.0"
RAW_REVERSAL = 4.25

THRESHOLD_EXPERIMENT = {
    "experiment_label": "V2_4_THRESHOLD_ONLY_HYPOTHESIS",
    "engine_version": "2.3.0",
    "hierarchy_reversal_atr_override": 4.25,
    "active_v2_4_profile": False,
    "accepted_candidate": False,
}


def load_helpers():
    path = ROOT / "scripts/tune_xauusd_h1_hierarchy.py"
    spec = importlib.util.spec_from_file_location(
        "fxn_v24_three_way_helpers", path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


HELPERS = load_helpers()


def me_counts(preds, labels) -> dict[str, int]:
    def is_me(tier, scope):
        return tier is SwingTier.MAJOR and scope is SwingScope.EXTERNAL

    pred_me = {
        (s.pivot_index, s.direction.value)
        for s in preds
        if s.confirmed and is_me(s.tier, s.scope)
    }
    truth_me = {
        (lab.pivot_index, lab.direction.value)
        for lab in labels
        if is_me(lab.tier, lab.scope)
    }
    return {
        "tp": len(pred_me & truth_me),
        "fp": len(pred_me - truth_me),
        "fn": len(truth_me - pred_me),
    }


def main() -> int:
    if "2.4.0" in SUPPORTED_VERSIONS:
        raise SystemExit(
            "REFUSED: unexpected active 2.4.0 profile; clean rejected "
            "implementation first"
        )
    if not CLOSE_BREAK.exists():
        raise SystemExit(
            f"REFUSED: missing {CLOSE_BREAK}; run close-break audit first"
        )

    specs = [
        spec
        for spec in load_manifest(MANIFEST)
        if spec.id in TRAIN_IDS and spec.split.upper() == "TRAIN"
    ]
    if [s.id for s in specs] != list(TRAIN_IDS):
        raise SystemExit("REFUSED: expected TRAIN 001-008 only")

    rows_23 = []
    rows_raw = []
    me23 = {"tp": 0, "fp": 0, "fn": 0}
    me_raw = {"tp": 0, "fp": 0, "fn": 0}
    for spec in specs:
        bars, labels = HELPERS._load_sample(spec, MANIFEST)
        p23, c23 = HELPERS._detect(spec, bars, version=V23)
        praw, craw = HELPERS._detect(
            spec, bars, version=V23, hierarchy_reversal_atr=RAW_REVERSAL
        )
        rows_23.append(
            HELPERS._evaluate_sample(spec, bars, labels, p23, c23, version=V23)
        )
        rows_raw.append(
            HELPERS._evaluate_sample(
                spec, bars, labels, praw, craw, version=V23
            )
        )
        for bucket, preds in ((me23, p23), (me_raw, praw)):
            counts = me_counts(preds, labels)
            for key, value in counts.items():
                bucket[key] += value

    agg23 = HELPERS._aggregate(rows_23)
    agg_raw = HELPERS._aggregate(rows_raw)
    close_break = json.loads(CLOSE_BREAK.read_text(encoding="utf-8"))

    report: dict[str, Any] = {
        "classification": "DEVELOPMENT_ONLY",
        "scope": "TRAIN_001_008_ONLY",
        "decision_status": "NOT_A_RELEASE_DECISION",
        "viable_v2_4_development_candidate": False,
        "active_v2_4_profile": False,
        "latest_version": LATEST_VERSION,
        "excluded_datasets_not_used": True,
        "generated_at_utc": datetime.now(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
        "samples": list(TRAIN_IDS),
        "forbidden_unused": [
            "XAUUSD_H1_009-012",
            "XAUUSD_H1_2026H1",
            "retrospective AI-draft windows",
            "post-2026H1 quarantine",
        ],
        "threshold_only_experiment": THRESHOLD_EXPERIMENT,
        "variants": {
            "v2_3": {
                "engine_version": V23,
                "hierarchy_reversal_atr": 5.0,
                "aggregate": agg23,
                "major_external_counts": me23,
                "location_counts": {
                    "tp": sum(int(r["true_positives"]) for r in rows_23),
                    "fp": sum(int(r["false_positives"]) for r in rows_23),
                    "fn": sum(int(r["false_negatives"]) for r in rows_23),
                },
            },
            "threshold_only_hypothesis": {
                **THRESHOLD_EXPERIMENT,
                "aggregate": agg_raw,
                "major_external_counts": me_raw,
                "location_counts": {
                    "tp": sum(int(r["true_positives"]) for r in rows_raw),
                    "fp": sum(int(r["false_positives"]) for r in rows_raw),
                    "fn": sum(int(r["false_negatives"]) for r in rows_raw),
                },
            },
            "predeclared_structural_rules": {
                "source": str(CLOSE_BREAK.relative_to(ROOT)),
                "supported_rules": close_break.get("supported_rules", []),
                "decision": close_break.get("decision"),
                "rule_results": {
                    name: {
                        "major_external_counts": result.get(
                            "major_external_counts"
                        ),
                        "major_external_metrics": result.get(
                            "major_external_metrics"
                        ),
                        "semantic_f1": result.get("aggregate", {}).get(
                            "semantic_f1"
                        ),
                        "passes_full_and_loso": result.get(
                            "passes_full_and_loso"
                        ),
                    }
                    for name, result in close_break.get(
                        "rule_results", {}
                    ).items()
                },
            },
        },
        "acceptance": {
            "viable_v2_4_development_candidate": False,
            "reason": (
                "Threshold-only 4.25 fails ME precision floor; Rules A–C fail "
                "full TRAIN and/or leave-one-sample-out acceptance. No engine "
                "2.4.0 profile accepted."
            ),
        },
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "wrote": str(OUTPUT),
                "viable_v2_4_development_candidate": False,
                "me23": me23,
                "me_threshold_only": me_raw,
                "supported_rules": close_break.get("supported_rules", []),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

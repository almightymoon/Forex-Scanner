#!/usr/bin/env python3
"""TRAIN-only audit of v2.3→raw-v2.4 major/external promotions.

DEVELOPMENT_ONLY / TRAIN_001_008_ONLY.
Does not use VALIDATION 009-012, 2026H1, AI-draft windows, or post-2026H1 data.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from swing_engine.datasets import load_manifest  # noqa: E402
from swing_engine.models import (  # noqa: E402
    SwingDirection,
    SwingHierarchyState,
    SwingScope,
    SwingTier,
)


MANIFEST = ROOT / "benchmarks/datasets/XAUUSD_H1.human.manifest.json"
OUTPUT = (
    ROOT
    / "benchmarks/reports/XAUUSD_H1_v2_4_major_external_promotion_audit.json"
)
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
        "fxn_v24_promotion_audit_helpers", path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


HELPERS = load_helpers()


def swing_key(swing) -> tuple[int, str]:
    return (int(swing.pivot_index), swing.direction.value)


def is_me(tier: SwingTier, scope: SwingScope) -> bool:
    return tier is SwingTier.MAJOR and scope is SwingScope.EXTERNAL


def extends_prior_external(swing, confirmed_externals: list) -> bool:
    prior = [
        prior.price
        for prior in confirmed_externals
        if prior.direction is swing.direction
    ]
    if not prior:
        return True
    if swing.direction is SwingDirection.HIGH:
        return swing.price >= max(prior)
    return swing.price <= min(prior)


def me_confusion(preds, labels) -> dict[str, int]:
    pred_me = {
        swing_key(s)
        for s in preds
        if s.confirmed and is_me(s.tier, s.scope)
    }
    truth_me = {
        swing_key(lab)
        for lab in labels
        if is_me(lab.tier, lab.scope)
    }
    return {
        "tp": len(pred_me & truth_me),
        "fp": len(pred_me - truth_me),
        "fn": len(truth_me - pred_me),
    }


def describe_swing(swing) -> dict[str, Any]:
    md = swing.metadata or {}
    return {
        "tier": swing.tier.value,
        "scope": swing.scope.value,
        "hierarchy_state": (
            swing.hierarchy_state.value if swing.hierarchy_state else None
        ),
        "confirmation_index": swing.confirmation_index,
        "hierarchy_confirmation_index": swing.hierarchy_confirmation_index,
        "hierarchy_revision_index": swing.hierarchy_revision_index,
        "hierarchy_reversal_atr": md.get("hierarchy_reversal_atr"),
        "structural_prominence_atr": md.get("structural_prominence_atr"),
        "leg_amplitude_atr": md.get("leg_atr"),
        "hierarchy_was_provisional": md.get("hierarchy_was_provisional"),
        "hierarchy_superseded_by_index": md.get("hierarchy_superseded_by_index"),
        "hierarchy_reason": md.get("hierarchy_reason"),
    }


def main() -> int:
    specs = [
        spec
        for spec in load_manifest(MANIFEST)
        if spec.id in TRAIN_IDS and spec.split.upper() == "TRAIN"
    ]
    if [s.id for s in specs] != list(TRAIN_IDS):
        raise SystemExit("REFUSED: expected TRAIN 001-008 only")

    changes: list[dict[str, Any]] = []
    promotions: list[dict[str, Any]] = []
    me_23 = {"tp": 0, "fp": 0, "fn": 0}
    me_24 = {"tp": 0, "fp": 0, "fn": 0}

    for spec in specs:
        bars, labels = HELPERS._load_sample(spec, MANIFEST)
        truth = {swing_key(lab): lab for lab in labels}
        pred23, _ = HELPERS._detect(spec, bars, version=V23)
        pred24, _ = HELPERS._detect(
            spec, bars, version=V23, hierarchy_reversal_atr=RAW_REVERSAL
        )
        for bucket, preds in ((me_23, pred23), (me_24, pred24)):
            counts = me_confusion(preds, labels)
            for key, value in counts.items():
                bucket[key] += value

        map23 = {swing_key(s): s for s in pred23 if s.confirmed}
        map24 = {swing_key(s): s for s in pred24 if s.confirmed}
        if set(map23) != set(map24):
            raise SystemExit(f"REFUSED: location drift on {spec.id}")

        ordered = sorted(
            map24.values(),
            key=lambda s: (
                s.hierarchy_confirmation_index
                if s.hierarchy_confirmation_index is not None
                else 10**9,
                s.pivot_index,
            ),
        )
        confirmed_externals: list = []
        for swing24 in ordered:
            key = swing_key(swing24)
            swing23 = map23[key]
            prior_relationship = {
                "prior_confirmed_external_count": len(confirmed_externals),
                "prior_same_direction_external_count": sum(
                    1
                    for prior in confirmed_externals
                    if prior.direction is swing24.direction
                ),
                "extends_or_breaks_prior_external": extends_prior_external(
                    swing24, confirmed_externals
                ),
            }
            semantic_changed = not (
                swing23.tier is swing24.tier
                and swing23.scope is swing24.scope
                and swing23.hierarchy_state is swing24.hierarchy_state
            )
            if semantic_changed:
                truth_lab = truth.get(key)
                a_me = is_me(swing23.tier, swing23.scope)
                b_me = is_me(swing24.tier, swing24.scope)
                truth_me = (
                    is_me(truth_lab.tier, truth_lab.scope)
                    if truth_lab is not None
                    else None
                )
                if b_me and not a_me:
                    if truth_me is True:
                        benefit = "beneficial"
                    elif truth_me is False:
                        benefit = "harmful"
                    else:
                        benefit = "location_false_positive"
                elif a_me and not b_me:
                    benefit = (
                        "harmful"
                        if truth_me is True
                        else "beneficial"
                        if truth_me is False
                        else "neutral"
                    )
                else:
                    benefit = "neutral"
                    if truth_lab is not None:
                        sem23 = (
                            swing23.tier is truth_lab.tier
                            and swing23.scope is truth_lab.scope
                        )
                        sem24 = (
                            swing24.tier is truth_lab.tier
                            and swing24.scope is truth_lab.scope
                        )
                        if sem24 and not sem23:
                            benefit = "beneficial"
                        elif sem23 and not sem24:
                            benefit = "harmful"

                row = {
                    "sample_id": spec.id,
                    "pivot_index": key[0],
                    "direction": key[1],
                    "v2_3": describe_swing(swing23),
                    "v2_4": describe_swing(swing24),
                    "truth": (
                        {
                            "tier": truth_lab.tier.value,
                            "scope": truth_lab.scope.value,
                        }
                        if truth_lab is not None
                        else None
                    ),
                    "benefit": benefit,
                    "major_external_promotion": bool(b_me and not a_me),
                    "prior_confirmed_major_relationship": prior_relationship,
                    "hierarchy_reversal_atr": (swing24.metadata or {}).get(
                        "hierarchy_reversal_atr"
                    ),
                    "prominence_atr": (swing24.metadata or {}).get(
                        "structural_prominence_atr"
                    ),
                    "leg_amplitude_atr": (swing24.metadata or {}).get("leg_atr"),
                    "confirmation_index": swing24.confirmation_index,
                    "hierarchy_confirmation_index": (
                        swing24.hierarchy_confirmation_index
                    ),
                    "superseded_or_provisional": {
                        "v2_3_state": (
                            swing23.hierarchy_state.value
                            if swing23.hierarchy_state
                            else None
                        ),
                        "v2_4_state": (
                            swing24.hierarchy_state.value
                            if swing24.hierarchy_state
                            else None
                        ),
                    },
                }
                changes.append(row)
                if row["major_external_promotion"]:
                    promotions.append(row)

            if swing24.hierarchy_state is SwingHierarchyState.CONFIRMED_MAJOR:
                # Raw v2.4 couples MAJOR→EXTERNAL, so confirmed majors form
                # the external sequence used for the structural discriminator.
                confirmed_externals.append(swing24)

    benefit_counts = Counter(row["benefit"] for row in promotions)
    extends_by_benefit = Counter(
        (
            row["benefit"],
            row["prior_confirmed_major_relationship"][
                "extends_or_breaks_prior_external"
            ],
        )
        for row in promotions
    )

    recovered_tp = sum(1 for row in promotions if row["benefit"] == "beneficial")
    introduced_fp = sum(1 for row in promotions if row["benefit"] == "harmful")
    remaining_fn = me_24["fn"]

    # Structural discriminator clarity: extends must keep all beneficial and
    # drop all harmful to be a clean separator.
    kept_if_extends = [
        row
        for row in promotions
        if row["prior_confirmed_major_relationship"][
            "extends_or_breaks_prior_external"
        ]
    ]
    dropped_if_extends = [
        row
        for row in promotions
        if not row["prior_confirmed_major_relationship"][
            "extends_or_breaks_prior_external"
        ]
    ]
    separator_clear = (
        all(row["benefit"] == "beneficial" for row in kept_if_extends)
        and all(row["benefit"] == "harmful" for row in dropped_if_extends)
        and recovered_tp > 0
        and introduced_fp > 0
    )

    report = {
        "classification": "DEVELOPMENT_ONLY",
        "scope": "TRAIN_001_008_ONLY",
        "decision_status": "NOT_A_RELEASE_DECISION",
        "viable_v2_4_development_candidate": False,
        "active_v2_4_profile": False,
        "latest_version": "2.3.0",
        "generated_at_utc": datetime.now(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
        "samples": list(TRAIN_IDS),
        "forbidden_unused": [
            "XAUUSD_H1_009-012",
            "XAUUSD_H1_2026H1",
            "retrospective AI-draft windows / evaluation report",
            "post-2026H1 quarantine candles",
            "locked or prospective benchmarks beyond TRAIN 001-008",
        ],
        "excluded_datasets_not_used": True,
        "baseline_engine": {
            "engine_version": V23,
            "hierarchy_reversal_atr": 5.0,
        },
        "threshold_only_experiment": THRESHOLD_EXPERIMENT,
        "major_external_confusion": {
            "v2_3": me_23,
            "threshold_only_hypothesis": me_24,
        },
        "promotion_summary": {
            "semantic_classification_changes": len(changes),
            "major_external_promotions": len(promotions),
            "beneficial_promotions": recovered_tp,
            "harmful_promotions": introduced_fp,
            "newly_recovered_major_external_true_positives": recovered_tp,
            "newly_introduced_major_external_false_positives": introduced_fp,
            "remaining_major_external_false_negatives": remaining_fn,
            "benefit_counts": dict(sorted(benefit_counts.items())),
            "extends_prior_external_by_benefit": {
                f"{benefit}:{extends}": count
                for (benefit, extends), count in sorted(
                    extends_by_benefit.items()
                )
            },
        },
        "structural_discriminator": {
            "hypothesis": (
                "EXTERNAL requires extending/breaking the prior confirmed "
                "external same-direction extreme; otherwise MAJOR/INTERNAL."
            ),
            "separates_beneficial_from_harmful": separator_clear,
            "if_require_extends_kept": {
                "count": len(kept_if_extends),
                "benefit_counts": dict(
                    Counter(row["benefit"] for row in kept_if_extends)
                ),
            },
            "if_require_extends_dropped": {
                "count": len(dropped_if_extends),
                "benefit_counts": dict(
                    Counter(row["benefit"] for row in dropped_if_extends)
                ),
            },
            "decision": (
                "REFUSE_4_25_THRESHOLD_CHANGE"
                if not separator_clear
                else "CANDIDATE_FOR_STRUCTURAL_REFINEMENT"
            ),
            "rationale": (
                "Prior-external extension does not cleanly separate newly "
                "recovered MAJOR/EXTERNAL true positives from newly introduced "
                "false positives on TRAIN 001-008; enabling it with 4.25 would "
                "be an unjustified coupling change rather than a validated "
                "structural fix."
                if not separator_clear
                else "Extension feature cleanly separates promotions."
            ),
        },
        "semantic_changes": changes,
        "major_external_promotions": promotions,
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"wrote": str(OUTPUT), "summary": report["promotion_summary"], "structural": report["structural_discriminator"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

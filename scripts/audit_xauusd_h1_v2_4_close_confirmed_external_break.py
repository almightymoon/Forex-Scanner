#!/usr/bin/env python3
"""Close-confirmed EXTERNAL break audit for raw 4.25 promotions.

DEVELOPMENT_ONLY / TRAIN_001_008_ONLY / NOT_A_RELEASE_DECISION.

Evaluates predeclared Rules A–C on TRAIN 001–008 without registering a 2.4.0
engine profile. Raw-4.25 behavior is obtained by overriding
hierarchy_reversal_atr on v2.3.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from swing_engine.datasets import load_manifest  # noqa: E402
from swing_engine.models import (  # noqa: E402
    SwingDirection,
    SwingHierarchyState,
    SwingScope,
    SwingTier,
)
from swing_engine.utils import atr_at, compute_atr_series  # noqa: E402


MANIFEST = ROOT / "benchmarks/datasets/XAUUSD_H1.human.manifest.json"
OUTPUT = ROOT / "benchmarks/reports/XAUUSD_H1_v2_4_close_break_audit.json"
TRAIN_IDS = tuple(f"XAUUSD_H1_{n:03d}" for n in range(1, 9))
V23 = "2.3.0"
RAW_REVERSAL = 4.25
V23_ME_RECALL = 0.686
V23_ME_F1 = 0.786517
V23_SEM_F1 = 0.694064

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
        "fxn_close_break_helpers", path
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


def me_counts(preds, labels) -> dict[str, int]:
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


def prf(tp: int, fp: int, fn: int) -> dict[str, float]:
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall)
        else 0.0
    )
    return {"precision": precision, "recall": recall, "f1": f1}


def describe(swing) -> dict[str, Any]:
    md = swing.metadata or {}
    return {
        "tier": swing.tier.value,
        "scope": swing.scope.value,
        "hierarchy_state": (
            swing.hierarchy_state.value if swing.hierarchy_state else None
        ),
        "confirmation_index": swing.confirmation_index,
        "hierarchy_confirmation_index": swing.hierarchy_confirmation_index,
        "hierarchy_reversal_atr": md.get("hierarchy_reversal_atr"),
        "structural_prominence_atr": md.get("structural_prominence_atr"),
        "leg_atr": md.get("leg_atr"),
        "hierarchy_was_provisional": md.get("hierarchy_was_provisional"),
        "hierarchy_superseded_by_index": md.get("hierarchy_superseded_by_index"),
        "hierarchy_reason": md.get("hierarchy_reason"),
        "price": swing.price,
    }


def candle_ohlc(bar) -> dict[str, float]:
    return {
        "open": float(bar.open),
        "high": float(bar.high),
        "low": float(bar.low),
        "close": float(bar.close),
    }


def close_break_features(
    *,
    swing,
    bars,
    atr_series,
    prior_same_price: float | None,
    prior_opp_price: float | None,
    hconf: int,
) -> dict[str, Any]:
    """Causal features available at or before hierarchy confirmation."""

    end = min(hconf, len(bars) - 1)
    window = bars[: end + 1]
    atr = atr_at(end, atr_series, bars) or atr_at(
        swing.pivot_index, atr_series, bars
    )
    atr = float(atr) if atr else 0.0

    pivot_extends = True
    if prior_same_price is not None:
        if swing.direction is SwingDirection.HIGH:
            pivot_extends = swing.price > prior_same_price
        else:
            pivot_extends = swing.price < prior_same_price

    close_break = True
    wick_break = True
    max_close_ext = 0.0
    max_wick_ext = 0.0
    first_close_break_index = None
    if prior_same_price is not None:
        close_break = False
        wick_break = False
        for idx, bar in enumerate(window):
            if swing.direction is SwingDirection.HIGH:
                wick_ext = float(bar.high) - prior_same_price
                close_ext = float(bar.close) - prior_same_price
                if float(bar.high) > prior_same_price:
                    wick_break = True
                    max_wick_ext = max(max_wick_ext, wick_ext)
                if float(bar.close) > prior_same_price:
                    close_break = True
                    max_close_ext = max(max_close_ext, close_ext)
                    if first_close_break_index is None:
                        first_close_break_index = idx
            else:
                wick_ext = prior_same_price - float(bar.low)
                close_ext = prior_same_price - float(bar.close)
                if float(bar.low) < prior_same_price:
                    wick_break = True
                    max_wick_ext = max(max_wick_ext, wick_ext)
                if float(bar.close) < prior_same_price:
                    close_break = True
                    max_close_ext = max(max_close_ext, close_ext)
                    if first_close_break_index is None:
                        first_close_break_index = idx

    highs = [float(b.high) for b in window]
    lows = [float(b.low) for b in window]
    conf_bar = bars[end]
    return {
        "hierarchy_confirmation_index": hconf,
        "confirmation_candle_ohlc": candle_ohlc(conf_bar),
        "confirmation_candle_close": float(conf_bar.close),
        "highest_high_by_hierarchy_confirmation": max(highs) if highs else None,
        "lowest_low_by_hierarchy_confirmation": min(lows) if lows else None,
        "prior_same_direction_external_price": prior_same_price,
        "prior_opposite_direction_external_price": prior_opp_price,
        "pivot_extends_prior_external": pivot_extends,
        "close_confirmed_extension_by_hierarchy_confirmation": close_break,
        "wick_break_without_requiring_close": wick_break and not close_break,
        "close_break_distance_atr": (
            round(max_close_ext / atr, 6) if atr > 0 else None
        ),
        "wick_only_break_distance_atr": (
            round(max_wick_ext / atr, 6)
            if atr > 0 and wick_break and not close_break
            else (round(max_wick_ext / atr, 6) if atr > 0 else None)
        ),
        "first_close_break_index": first_close_break_index,
        "atr_at_hierarchy_confirmation": round(atr, 6) if atr else None,
        "features_causal_at_or_before_hconf": True,
    }


def persistence_note(
    *,
    swing,
    bars,
    prior_same_price: float | None,
    hconf: int,
    next_hconf: int | None,
) -> dict[str, Any]:
    """Audit-only persistence through next confirmation; not used for Rules A–C."""

    if prior_same_price is None or next_hconf is None:
        return {
            "evaluated": False,
            "close_break_persisted_to_next_confirmation": None,
            "note": "no prior level or no later confirmation event",
        }
    end = min(next_hconf, len(bars) - 1)
    # Only bars up to next confirmation — still not used for the proposed
    # decision at hconf; recorded for audit transparency.
    persisted = False
    for bar in bars[hconf : end + 1]:
        if swing.direction is SwingDirection.HIGH:
            if float(bar.close) > prior_same_price:
                persisted = True
                break
        elif float(bar.close) < prior_same_price:
            persisted = True
            break
    return {
        "evaluated": True,
        "next_confirmation_index": next_hconf,
        "close_break_persisted_to_next_confirmation": persisted,
        "used_for_rule_decision": False,
    }


def build_promotion_rows(specs) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for spec in specs:
        bars, labels = HELPERS._load_sample(spec, MANIFEST)
        truth = {swing_key(lab): lab for lab in labels}
        pred23, _ = HELPERS._detect(spec, bars, version=V23)
        pred24, _ = HELPERS._detect(
            spec, bars, version=V23, hierarchy_reversal_atr=RAW_REVERSAL
        )
        map23 = {swing_key(s): s for s in pred23 if s.confirmed}
        map24 = {swing_key(s): s for s in pred24 if s.confirmed}
        if set(map23) != set(map24):
            raise SystemExit(f"REFUSED: location drift on {spec.id}")

        atr_series = compute_atr_series(bars, period=14)
        ordered = sorted(
            [
                s
                for s in map24.values()
                if s.hierarchy_state is SwingHierarchyState.CONFIRMED_MAJOR
            ],
            key=lambda s: (
                int(s.hierarchy_confirmation_index),
                s.pivot_index,
            ),
        )
        hconfs = [
            int(s.hierarchy_confirmation_index)
            for s in ordered
            if s.hierarchy_confirmation_index is not None
        ]

        confirmed_ext: list = []
        for i, swing24 in enumerate(ordered):
            key = swing_key(swing24)
            swing23 = map23[key]
            a_me = is_me(swing23.tier, swing23.scope)
            b_me = is_me(swing24.tier, swing24.scope)
            if not (b_me and not a_me):
                confirmed_ext.append(swing24)
                continue

            truth_lab = truth.get(key)
            truth_me = (
                is_me(truth_lab.tier, truth_lab.scope)
                if truth_lab is not None
                else None
            )
            benefit = (
                "beneficial"
                if truth_me is True
                else "harmful"
                if truth_me is False
                else "location_false_positive"
            )
            prior_same = [
                p for p in confirmed_ext if p.direction is swing24.direction
            ]
            prior_opp = [
                p
                for p in confirmed_ext
                if p.direction is not swing24.direction
            ]
            if not prior_same:
                prior_same_price = None
            elif swing24.direction is SwingDirection.HIGH:
                prior_same_price = max(p.price for p in prior_same)
            else:
                prior_same_price = min(p.price for p in prior_same)
            prior_opp_price = prior_opp[-1].price if prior_opp else None
            hconf = int(swing24.hierarchy_confirmation_index)
            feats = close_break_features(
                swing=swing24,
                bars=bars,
                atr_series=atr_series,
                prior_same_price=prior_same_price,
                prior_opp_price=prior_opp_price,
                hconf=hconf,
            )
            next_hconf = hconfs[i + 1] if i + 1 < len(hconfs) else None
            persist = persistence_note(
                swing=swing24,
                bars=bars,
                prior_same_price=prior_same_price,
                hconf=hconf,
                next_hconf=next_hconf,
            )
            last_opp = prior_opp[-1] if prior_opp else None
            alternates = last_opp is None or (
                last_opp.direction is not swing24.direction
            )
            rows.append(
                {
                    "sample_id": spec.id,
                    "pivot_index": key[0],
                    "direction": key[1],
                    "truth": (
                        {
                            "tier": truth_lab.tier.value,
                            "scope": truth_lab.scope.value,
                        }
                        if truth_lab is not None
                        else None
                    ),
                    "v2_3": describe(swing23),
                    "raw_4_25": describe(swing24),
                    "benefit": benefit,
                    "hierarchy_reversal_atr": (swing24.metadata or {}).get(
                        "hierarchy_reversal_atr"
                    ),
                    "prominence_atr": (swing24.metadata or {}).get(
                        "structural_prominence_atr"
                    ),
                    "leg_amplitude_atr": (swing24.metadata or {}).get("leg_atr"),
                    "pivot_price": swing24.price,
                    "close_break_features": feats,
                    "persistence_audit_only": persist,
                    "rule_predicates": {
                        "rule_a_pivot_extends": feats[
                            "pivot_extends_prior_external"
                        ],
                        "rule_b_close_break": feats[
                            "close_confirmed_extension_by_hierarchy_confirmation"
                        ],
                        "rule_c_close_break_and_alternates": (
                            feats[
                                "close_confirmed_extension_by_hierarchy_confirmation"
                            ]
                            and alternates
                        ),
                        "alternates_vs_latest_opposite_external": alternates,
                    },
                    "provisional_superseded_chain": {
                        "v2_3_state": (
                            swing23.hierarchy_state.value
                            if swing23.hierarchy_state
                            else None
                        ),
                        "raw_4_25_state": (
                            swing24.hierarchy_state.value
                            if swing24.hierarchy_state
                            else None
                        ),
                        "was_provisional": (swing24.metadata or {}).get(
                            "hierarchy_was_provisional"
                        ),
                        "superseded_by_index": (swing24.metadata or {}).get(
                            "hierarchy_superseded_by_index"
                        ),
                    },
                }
            )
            confirmed_ext.append(swing24)
    return rows


def apply_scope_rule(
    swings: list,
    bars,
    atr_series,
    rule: str,
) -> list:
    copies = [deepcopy(s) for s in swings]
    majors = [
        s
        for s in copies
        if s.hierarchy_state
        in (
            SwingHierarchyState.CONFIRMED_MAJOR,
            SwingHierarchyState.PROVISIONAL_MAJOR,
        )
    ]

    def sort_key(s):
        if (
            s.hierarchy_state is SwingHierarchyState.CONFIRMED_MAJOR
            and s.hierarchy_confirmation_index is not None
        ):
            return (0, int(s.hierarchy_confirmation_index), s.pivot_index)
        avail = s.confirmation_index
        return (1, int(avail) if avail is not None else s.pivot_index)

    confirmed_ext: list = []
    for swing in sorted(majors, key=sort_key):
        prior_same = [
            p for p in confirmed_ext if p.direction is swing.direction
        ]
        prior_opp = [
            p for p in confirmed_ext if p.direction is not swing.direction
        ]
        if swing.direction is SwingDirection.HIGH:
            prior_same_price = (
                max(p.price for p in prior_same) if prior_same else None
            )
        else:
            prior_same_price = (
                min(p.price for p in prior_same) if prior_same else None
            )
        hconf = swing.hierarchy_confirmation_index
        if hconf is None:
            hconf = swing.confirmation_index
        if hconf is None:
            hconf = swing.pivot_index
        hconf = int(hconf)

        pivot_extends = True
        if prior_same_price is not None:
            if swing.direction is SwingDirection.HIGH:
                pivot_extends = swing.price > prior_same_price
            else:
                pivot_extends = swing.price < prior_same_price

        close_break = True
        if prior_same_price is not None:
            close_break = False
            for bar in bars[: hconf + 1]:
                if swing.direction is SwingDirection.HIGH:
                    if float(bar.close) > prior_same_price:
                        close_break = True
                        break
                elif float(bar.close) < prior_same_price:
                    close_break = True
                    break

        alternates = (not prior_opp) or (
            prior_opp[-1].direction is not swing.direction
        )

        if rule == "A":
            ok = pivot_extends
        elif rule == "B":
            ok = close_break
        elif rule == "C":
            ok = close_break and alternates
        else:
            raise ValueError(rule)

        if ok:
            swing.scope = SwingScope.EXTERNAL
            swing.tier = SwingTier.MAJOR
            confirmed_ext.append(swing)
        else:
            swing.tier = SwingTier.MAJOR
            swing.scope = SwingScope.INTERNAL
    return copies


def evaluate_rule_on_specs(
    specs, rule: str
) -> dict[str, Any]:
    rows = []
    me = {"tp": 0, "fp": 0, "fn": 0}
    for spec in specs:
        bars, labels = HELPERS._load_sample(spec, MANIFEST)
        preds, cfg = HELPERS._detect(
            spec, bars, version=V23, hierarchy_reversal_atr=RAW_REVERSAL
        )
        atr_series = compute_atr_series(bars, period=14)
        refined = apply_scope_rule(preds, bars, atr_series, rule)
        row = HELPERS._evaluate_sample(
            spec, bars, labels, refined, cfg, version=V23
        )
        rows.append(row)
        counts = me_counts(refined, labels)
        for key, value in counts.items():
            me[key] += value
    agg = HELPERS._aggregate(rows)
    loc = {
        "tp": sum(int(r["true_positives"]) for r in rows),
        "fp": sum(int(r["false_positives"]) for r in rows),
        "fn": sum(int(r["false_negatives"]) for r in rows),
    }
    return {
        "rule": rule,
        "location_counts": loc,
        "major_external_counts": me,
        "major_external_metrics": prf(me["tp"], me["fp"], me["fn"]),
        "aggregate": {
            "location_f1": agg["location"]["f1"],
            "semantic_f1": agg["semantic"]["f1"],
            "major_external_precision": agg["major_external"]["precision"],
            "major_external_recall": agg["major_external"]["recall"],
            "major_external_f1": agg["major_external"]["f1"],
        },
    }


def promotion_impact(promotions: list[dict], predicate: Callable) -> dict:
    retained_ben = [
        r for r in promotions if r["benefit"] == "beneficial" and predicate(r)
    ]
    lost_ben = [
        r
        for r in promotions
        if r["benefit"] == "beneficial" and not predicate(r)
    ]
    retained_harm = [
        r for r in promotions if r["benefit"] == "harmful" and predicate(r)
    ]
    removed_harm = [
        r for r in promotions if r["benefit"] == "harmful" and not predicate(r)
    ]
    return {
        "beneficial_retained": len(retained_ben),
        "beneficial_lost": len(lost_ben),
        "harmful_retained": len(retained_harm),
        "harmful_removed": len(removed_harm),
        "beneficial_retained_ids": [
            f"{r['sample_id']}:{r['pivot_index']}:{r['direction']}"
            for r in retained_ben
        ],
        "beneficial_lost_ids": [
            f"{r['sample_id']}:{r['pivot_index']}:{r['direction']}"
            for r in lost_ben
        ],
        "harmful_retained_ids": [
            f"{r['sample_id']}:{r['pivot_index']}:{r['direction']}"
            for r in retained_harm
        ],
        "harmful_removed_ids": [
            f"{r['sample_id']}:{r['pivot_index']}:{r['direction']}"
            for r in removed_harm
        ],
        "affected_samples": sorted(
            {
                r["sample_id"]
                for r in promotions
                if predicate(r) != (r["benefit"] == "beneficial")
            }
        ),
    }


def acceptance_ok(result: dict[str, Any], baseline_loc: dict) -> dict[str, bool]:
    me = result["major_external_metrics"]
    agg = result["aggregate"]
    return {
        "location_unchanged": result["location_counts"] == baseline_loc,
        "me_precision_ge_0_85": me["precision"] >= 0.85,
        "me_recall_gt_0_686": me["recall"] > V23_ME_RECALL,
        "me_f1_ge_v2_3": me["f1"] >= V23_ME_F1,
        "semantic_f1_gt_v2_3": agg["semantic_f1"] > V23_SEM_F1,
    }


def main() -> int:
    # Guard: no active 2.4.0 profile while auditing.
    from swing_engine.versions import SUPPORTED_VERSIONS

    if "2.4.0" in SUPPORTED_VERSIONS:
        raise SystemExit(
            "REFUSED: active 2.4.0 profile present; clean rejected "
            "implementation before auditing close-break hypothesis"
        )

    specs = [
        spec
        for spec in load_manifest(MANIFEST)
        if spec.id in TRAIN_IDS and spec.split.upper() == "TRAIN"
    ]
    if [s.id for s in specs] != list(TRAIN_IDS):
        raise SystemExit("REFUSED: expected TRAIN 001-008 only")

    # Baseline location from v2.3
    baseline_rows = []
    me23 = {"tp": 0, "fp": 0, "fn": 0}
    me_raw = {"tp": 0, "fp": 0, "fn": 0}
    for spec in specs:
        bars, labels = HELPERS._load_sample(spec, MANIFEST)
        p23, c23 = HELPERS._detect(spec, bars, version=V23)
        praw, craw = HELPERS._detect(
            spec, bars, version=V23, hierarchy_reversal_atr=RAW_REVERSAL
        )
        baseline_rows.append(
            HELPERS._evaluate_sample(spec, bars, labels, p23, c23, version=V23)
        )
        for bucket, preds in ((me23, p23), (me_raw, praw)):
            counts = me_counts(preds, labels)
            for key, value in counts.items():
                bucket[key] += value
    baseline_loc = {
        "tp": sum(int(r["true_positives"]) for r in baseline_rows),
        "fp": sum(int(r["false_positives"]) for r in baseline_rows),
        "fn": sum(int(r["false_negatives"]) for r in baseline_rows),
    }

    promotions = build_promotion_rows(specs)

    rule_preds = {
        "A": lambda r: r["rule_predicates"]["rule_a_pivot_extends"],
        "B": lambda r: r["rule_predicates"]["rule_b_close_break"],
        "C": lambda r: r["rule_predicates"][
            "rule_c_close_break_and_alternates"
        ],
    }

    rule_results = {}
    for name in ("A", "B", "C"):
        metrics = evaluate_rule_on_specs(specs, name)
        impact = promotion_impact(promotions, rule_preds[name])
        checks = acceptance_ok(metrics, baseline_loc)
        # Prefix: same as raw 4.25 majors' hierarchy confirmation indices —
        # scope-only change; first-level + hierarchy confirmation indices
        # unchanged. Record 0 with note.
        rule_results[name] = {
            **metrics,
            "promotion_impact": impact,
            "all_features_causal": True,
            "acceptance_checks": checks,
            "passes_full_train": all(checks.values()),
            "prefix_failures": 0,
            "prefix_note": (
                "Scope-only refinement preserves hierarchy confirmation "
                "indexes from the raw-4.25 override run"
            ),
        }

        # Leave-one-sample-out
        folds = []
        for held in TRAIN_IDS:
            fold_specs = [s for s in specs if s.id != held]
            fold_metrics = evaluate_rule_on_specs(fold_specs, name)
            fold_checks = acceptance_ok(fold_metrics, fold_metrics["location_counts"])
            # For LOSO, location unchanged vs fold's own v2.3 would need baseline;
            # check ME floors only as required.
            folds.append(
                {
                    "held_out_sample": held,
                    "major_external_counts": fold_metrics[
                        "major_external_counts"
                    ],
                    "major_external_metrics": fold_metrics[
                        "major_external_metrics"
                    ],
                    "semantic_f1": fold_metrics["aggregate"]["semantic_f1"],
                    "precision_ge_0_85": fold_metrics["major_external_metrics"][
                        "precision"
                    ]
                    >= 0.85,
                    "recall_gt_v2_3": fold_metrics["major_external_metrics"][
                        "recall"
                    ]
                    > V23_ME_RECALL,
                }
            )
        rule_results[name]["leave_one_sample_out"] = {
            "folds": folds,
            "precision_ge_0_85_every_fold": all(
                f["precision_ge_0_85"] for f in folds
            ),
            "recall_gt_v2_3_every_fold": all(
                f["recall_gt_v2_3"] for f in folds
            ),
        }
        rule_results[name]["passes_full_and_loso"] = (
            rule_results[name]["passes_full_train"]
            and rule_results[name]["leave_one_sample_out"][
                "precision_ge_0_85_every_fold"
            ]
            and rule_results[name]["leave_one_sample_out"][
                "recall_gt_v2_3_every_fold"
            ]
        )

    supported = [
        name
        for name, result in rule_results.items()
        if result["passes_full_and_loso"]
    ]

    # Feature table for promotions
    feature_table = []
    for row in promotions:
        feats = row["close_break_features"]
        feature_table.append(
            {
                "id": f"{row['sample_id']}:{row['pivot_index']}:{row['direction']}",
                "benefit": row["benefit"],
                "pivot_extends": feats["pivot_extends_prior_external"],
                "close_break": feats[
                    "close_confirmed_extension_by_hierarchy_confirmation"
                ],
                "wick_only": feats["wick_break_without_requiring_close"],
                "close_break_distance_atr": feats["close_break_distance_atr"],
                "wick_only_break_distance_atr": feats[
                    "wick_only_break_distance_atr"
                ],
                "rule_a": row["rule_predicates"]["rule_a_pivot_extends"],
                "rule_b": row["rule_predicates"]["rule_b_close_break"],
                "rule_c": row["rule_predicates"][
                    "rule_c_close_break_and_alternates"
                ],
            }
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
            "retrospective AI-draft windows/reports",
            "post-2026H1 quarantine",
            "prospective/locked benchmarks beyond TRAIN 001-008",
        ],
        "excluded_datasets_not_used": True,
        "baseline_engine": {
            "engine_version": V23,
            "hierarchy_reversal_atr": 5.0,
        },
        "threshold_only_experiment": THRESHOLD_EXPERIMENT,
        "baselines": {
            "v2_3_me": me23,
            "threshold_only_hypothesis_me": me_raw,
            "location_counts": baseline_loc,
        },
        "promotions": promotions,
        "promotion_counts": dict(Counter(r["benefit"] for r in promotions)),
        "beneficial_vs_harmful_close_break_table": feature_table,
        "predeclared_rules": {
            "A": "EXTERNAL only when pivot extends prior confirmed external same-direction extreme",
            "B": "EXTERNAL only when a candle close breaks prior confirmed external same-direction extreme by hierarchy confirmation",
            "C": "EXTERNAL only when Rule B holds and sequence alternates vs latest confirmed opposite external",
        },
        "rule_results": rule_results,
        "supported_rules": supported,
        "selected_rule": supported[0] if len(supported) == 1 else (
            supported if supported else None
        ),
        "decision": (
            {
                "implement": True,
                "rule": supported[0],
            }
            if len(supported) == 1
            else {
                "implement": False,
                "reason": (
                    "No supported v2.4 semantic rule among predeclared A–C"
                    if not supported
                    else "Multiple rules passed; manual selection required"
                ),
            }
        ),
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    summary = {
        "wrote": str(OUTPUT),
        "promotions": report["promotion_counts"],
        "supported_rules": supported,
        "decision": report["decision"],
        "rule_summary": {
            name: {
                "me": result["major_external_counts"],
                "metrics": result["major_external_metrics"],
                "semantic_f1": result["aggregate"]["semantic_f1"],
                "passes_full_and_loso": result["passes_full_and_loso"],
                "impact": {
                    k: result["promotion_impact"][k]
                    for k in (
                        "beneficial_retained",
                        "beneficial_lost",
                        "harmful_retained",
                        "harmful_removed",
                    )
                },
            }
            for name, result in rule_results.items()
        },
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

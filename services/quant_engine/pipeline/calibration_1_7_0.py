"""Pipeline 1.7.0 — Arm H2 exit / payoff geometry.

Frozen 1.4.0 analysis unchanged. This module only remaps take-profit from the
original stop distance (same entry + SL). Execution policy remains
signal_close / sl_first / zero costs.

Selection and success criteria match H1/H3 for comparability.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable, Sequence

from services.quant_engine.pipeline.calibration_1_5_0 import (
    BASELINE_1_4_0_TEST,
    DEFAULT_SELECTION,
    DEFAULT_TEST_SUCCESS,
    SelectionCriteria,
    TestSuccessCriteria,
    evaluate_test_success,
)

EXPERIMENT_PIPELINE_VERSION = "1.7.0"
EXPERIMENT_ARM = "H2"
FROZEN_BASELINE_VERSION = "1.4.0"


@dataclass(frozen=True)
class ExitPolicy:
    """TP remap relative to original stop distance. ``target_rr=None`` = baseline levels."""

    name: str
    target_rr: float | None = None

    def levels(self, *, direction: str, entry: float, stop_loss: float, take_profit: float) -> tuple[float, float]:
        if self.target_rr is None:
            return stop_loss, take_profit
        risk = abs(entry - stop_loss)
        if risk <= 0:
            return stop_loss, take_profit
        d = direction.lower()
        if d == "buy":
            return stop_loss, entry + self.target_rr * risk
        return stop_loss, entry - self.target_rr * risk

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExitPolicy":
        return cls(name=data["name"], target_rr=data.get("target_rr"))


# Predeclared candidates — fixed before looking at VALIDATION metrics for selection.
CANDIDATE_POLICIES: tuple[ExitPolicy, ...] = (
    ExitPolicy("h2_baseline_rr_133", target_rr=None),  # original ~1.333 R from ATR 2/1.5
    ExitPolicy("h2_tp_rr_1_0", target_rr=1.0),
    ExitPolicy("h2_tp_rr_1_5", target_rr=1.5),
    ExitPolicy("h2_tp_rr_2_0", target_rr=2.0),
    ExitPolicy("h2_tp_rr_2_5", target_rr=2.5),
    ExitPolicy("h2_tp_rr_3_0", target_rr=3.0),
    ExitPolicy("h2_tp_rr_0_75", target_rr=0.75),
)


def select_policy(
    validation_metrics_by_name: dict[str, dict[str, Any]],
    *,
    criteria: SelectionCriteria = DEFAULT_SELECTION,
    candidates: Sequence[ExitPolicy] = CANDIDATE_POLICIES,
) -> dict[str, Any]:
    ranked: list[tuple[tuple, ExitPolicy, dict[str, Any]]] = []
    for policy in candidates:
        m = validation_metrics_by_name.get(policy.name)
        if not m:
            continue
        n = int(m.get("total_trades") or 0)
        exp = float(m.get("expectancy") or 0.0)
        raw_pf = m.get("profit_factor")
        pf = float(raw_pf) if raw_pf is not None else 0.0
        qualifies = (
            n >= criteria.min_trades
            and exp >= criteria.min_expectancy
            and pf >= criteria.min_profit_factor
        )
        key = (0 if qualifies else 1, -exp, -pf, -n, policy.name)
        ranked.append((key, policy, m))

    ranked.sort(key=lambda x: x[0])
    if not ranked:
        return {
            "qualified": False,
            "selected": None,
            "reason": "no_candidate_metrics",
            "criteria": asdict(criteria),
        }

    best_key, best_policy, best_m = ranked[0]
    qualified = best_key[0] == 0
    return {
        "qualified": qualified,
        "selected": best_policy.to_dict(),
        "validation_metrics": best_m,
        "reason": "met_validation_gates" if qualified else "no_policy_met_gates_diagnostic_best",
        "criteria": asdict(criteria),
        "ranking": [
            {
                "name": p.name,
                "qualified": key[0] == 0,
                "expectancy": validation_metrics_by_name[p.name].get("expectancy"),
                "profit_factor": validation_metrics_by_name[p.name].get("profit_factor"),
                "total_trades": validation_metrics_by_name[p.name].get("total_trades"),
                "total_r": validation_metrics_by_name[p.name].get("total_r"),
            }
            for key, p, _ in ranked
        ],
    }


def policy_by_name(name: str, candidates: Iterable[ExitPolicy] = CANDIDATE_POLICIES) -> ExitPolicy:
    for p in candidates:
        if p.name == name:
            return p
    raise KeyError(name)


__all__ = [
    "BASELINE_1_4_0_TEST",
    "CANDIDATE_POLICIES",
    "DEFAULT_SELECTION",
    "DEFAULT_TEST_SUCCESS",
    "EXPERIMENT_ARM",
    "EXPERIMENT_PIPELINE_VERSION",
    "ExitPolicy",
    "FROZEN_BASELINE_VERSION",
    "SelectionCriteria",
    "TestSuccessCriteria",
    "evaluate_test_success",
    "policy_by_name",
    "select_policy",
]

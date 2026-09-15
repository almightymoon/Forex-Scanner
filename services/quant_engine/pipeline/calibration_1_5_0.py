"""Pipeline 1.5.0 — Arm H1 score/confidence emit calibration.

Frozen baseline analysis remains 1.4.0. This module only defines **emit gates**
(which scored setups are traded). It does not change DecisionEngine weights,
zone ranking, FVG/OB lifecycle, or SL/TP construction.

Selection and success criteria are predeclared here — fit only on TRAIN/VALIDATION.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable, Sequence


EXPERIMENT_PIPELINE_VERSION = "1.5.0"
EXPERIMENT_ARM = "H1"
FROZEN_BASELINE_VERSION = "1.4.0"

# 1.4.0 BASE locked TEST reference (docs/OOS_VALIDATION_REPORT_1.4.0.md)
BASELINE_1_4_0_TEST = {
    "trades": 246,
    "win_rate": 38.6,
    "profit_factor": 0.761,
    "expectancy": -0.091,
    "total_r": -22.434,
    "max_drawdown_r": 30.329,
}

# Predeclared: TEST may not be worse than baseline total R by more than this.
TEST_TOTAL_R_TOLERANCE = 5.0


@dataclass(frozen=True)
class EmitPolicy:
    """Hard score/confidence band for signal emission."""

    name: str
    min_score: int = 70
    max_score: int = 100
    min_confidence: float = 0.0
    max_confidence: float = 1.0

    def allows(self, score: float, confidence: float) -> bool:
        return (
            self.min_score <= score <= self.max_score
            and self.min_confidence <= confidence <= self.max_confidence
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# Predeclared candidate arms — enumerated before any TRAIN/VAL metrics are used.
CANDIDATE_POLICIES: tuple[EmitPolicy, ...] = (
    EmitPolicy("h1_baseline_min70", min_score=70, max_score=100),
    EmitPolicy("h1_score_cap_94", min_score=70, max_score=94),
    EmitPolicy("h1_score_cap_84", min_score=70, max_score=84),
    EmitPolicy("h1_score_band_71_84", min_score=71, max_score=84),
    EmitPolicy("h1_score_band_71_94", min_score=71, max_score=94),
    EmitPolicy("h1_excl_high_conf", min_score=70, max_score=100, max_confidence=0.84),
    EmitPolicy("h1_conf_lt_060", min_score=70, max_score=100, max_confidence=0.59),
    EmitPolicy(
        "h1_score_cap_84_conf_cap_084",
        min_score=70,
        max_score=84,
        max_confidence=0.84,
    ),
)


@dataclass(frozen=True)
class SelectionCriteria:
    """Predeclared VALIDATION gate for promoting a policy to TEST."""

    min_expectancy: float = 0.0
    min_profit_factor: float = 1.0
    min_trades: int = 20


DEFAULT_SELECTION = SelectionCriteria()


@dataclass(frozen=True)
class TestSuccessCriteria:
    """Predeclared TEST success — evaluated only after selection is locked."""

    require_positive_expectancy: bool = True
    require_pf_at_least: float = 1.0
    max_total_r_worse_than_baseline: float = TEST_TOTAL_R_TOLERANCE


DEFAULT_TEST_SUCCESS = TestSuccessCriteria()


def filter_trades(
    trades: Sequence[dict[str, Any]],
    policy: EmitPolicy,
) -> list[dict[str, Any]]:
    return [
        t
        for t in trades
        if policy.allows(float(t["score"]), float(t.get("confidence", 0.0)))
    ]


def select_policy(
    validation_metrics_by_name: dict[str, dict[str, Any]],
    *,
    criteria: SelectionCriteria = DEFAULT_SELECTION,
    candidates: Sequence[EmitPolicy] = CANDIDATE_POLICIES,
) -> dict[str, Any]:
    """Pick a policy from VALIDATION metrics only.

    Among policies meeting expectancy / PF / n floors, maximize expectancy,
    then PF, then trade count, then name. If none qualify, return
    ``qualified=False`` and the best expectancy policy for diagnostics only.
    """
    ranked: list[tuple[tuple, EmitPolicy, dict[str, Any]]] = []
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
        # Sort key: qualified first, then exp, pf, n, name
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
            }
            for key, p, _ in ranked
        ],
    }


def evaluate_test_success(
    metrics: dict[str, Any],
    *,
    criteria: TestSuccessCriteria = DEFAULT_TEST_SUCCESS,
    baseline: dict[str, Any] = BASELINE_1_4_0_TEST,
) -> dict[str, Any]:
    exp = float(metrics.get("expectancy") or 0.0)
    raw_pf = metrics.get("profit_factor")
    pf = float(raw_pf) if raw_pf is not None else 0.0
    total_r = float(metrics.get("total_r") or 0.0)
    baseline_r = float(baseline["total_r"])
    floor_r = baseline_r - criteria.max_total_r_worse_than_baseline

    checks = {
        "positive_expectancy": exp > 0.0 if criteria.require_positive_expectancy else True,
        "profit_factor": pf >= criteria.require_pf_at_least,
        "total_r_not_worse_than_baseline_tolerance": total_r >= floor_r,
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "criteria": asdict(criteria),
        "baseline_total_r": baseline_r,
        "total_r_floor": floor_r,
        "observed": {
            "expectancy": exp,
            "profit_factor": pf,
            "total_r": total_r,
            "total_trades": metrics.get("total_trades"),
            "win_rate": metrics.get("win_rate"),
        },
    }


def policy_by_name(name: str, candidates: Iterable[EmitPolicy] = CANDIDATE_POLICIES) -> EmitPolicy:
    for p in candidates:
        if p.name == name:
            return p
    raise KeyError(f"unknown emit policy: {name}")

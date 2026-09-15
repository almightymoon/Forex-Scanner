"""Pipeline 1.8.0 — Arm H4 zone ranking / liquidity emit gating.

Frozen 1.4.0 analysis unchanged. Gates use forensics-compatible labels:
primary_rank and liquidity_relation from zone_context enrichment.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Sequence

from services.quant_engine.pipeline.calibration_1_5_0 import (
    BASELINE_1_4_0_TEST,
    DEFAULT_SELECTION,
    DEFAULT_TEST_SUCCESS,
    SelectionCriteria,
    TestSuccessCriteria,
    evaluate_test_success,
)

EXPERIMENT_PIPELINE_VERSION = "1.8.0"
EXPERIMENT_ARM = "H4"
FROZEN_BASELINE_VERSION = "1.4.0"

_ALL_LIQ = frozenset({"ASSOCIATED_SWEEP", "NEAR_RELEVANT", "NONE", "UNKNOWN", None})


@dataclass(frozen=True)
class EmitPolicy:
    name: str
    max_primary_rank: int | None = None  # None = no rank filter; else primary_rank <= max
    require_primary_rank: bool = False  # if True, drop trades with missing rank
    liquidity_allowed: frozenset[str | None] = field(default_factory=lambda: frozenset(_ALL_LIQ))
    exclude_liquidity: frozenset[str] = field(default_factory=frozenset)

    def allows(self, trade: dict[str, Any]) -> bool:
        rank = trade.get("primary_rank")
        if self.require_primary_rank and rank is None:
            return False
        if self.max_primary_rank is not None:
            if rank is None:
                return False
            if int(rank) > self.max_primary_rank:
                return False
        liq = trade.get("liquidity_relation")
        if liq in self.exclude_liquidity:
            return False
        # Allow None/missing as UNKNOWN bucket if UNKNOWN in allowed set
        key = liq if liq is not None else "UNKNOWN"
        allowed = {("UNKNOWN" if x is None else x) for x in self.liquidity_allowed}
        return key in allowed

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "max_primary_rank": self.max_primary_rank,
            "require_primary_rank": self.require_primary_rank,
            "liquidity_allowed": sorted(x for x in self.liquidity_allowed if x is not None),
            "exclude_liquidity": sorted(self.exclude_liquidity),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EmitPolicy":
        allowed = data.get("liquidity_allowed")
        return cls(
            name=data["name"],
            max_primary_rank=data.get("max_primary_rank"),
            require_primary_rank=bool(data.get("require_primary_rank", False)),
            liquidity_allowed=frozenset(allowed) if allowed is not None else frozenset(_ALL_LIQ),
            exclude_liquidity=frozenset(data.get("exclude_liquidity") or []),
        )


CANDIDATE_POLICIES: tuple[EmitPolicy, ...] = (
    EmitPolicy("h4_baseline_all"),
    EmitPolicy("h4_rank1_only", max_primary_rank=1, require_primary_rank=True),
    EmitPolicy("h4_rank_le_2", max_primary_rank=2, require_primary_rank=True),
    EmitPolicy(
        "h4_exclude_associated_sweep",
        exclude_liquidity=frozenset({"ASSOCIATED_SWEEP"}),
    ),
    EmitPolicy(
        "h4_liquidity_none_only",
        liquidity_allowed=frozenset({"NONE"}),
    ),
    EmitPolicy(
        "h4_liquidity_near_or_none",
        liquidity_allowed=frozenset({"NONE", "NEAR_RELEVANT"}),
    ),
    EmitPolicy(
        "h4_rank1_exclude_sweep",
        max_primary_rank=1,
        require_primary_rank=True,
        exclude_liquidity=frozenset({"ASSOCIATED_SWEEP"}),
    ),
    EmitPolicy(
        "h4_rank1_liquidity_none",
        max_primary_rank=1,
        require_primary_rank=True,
        liquidity_allowed=frozenset({"NONE"}),
    ),
)


def filter_trades(trades: Sequence[dict[str, Any]], policy: EmitPolicy) -> list[dict[str, Any]]:
    return [t for t in trades if policy.allows(t)]


def select_policy(
    validation_metrics_by_name: dict[str, dict[str, Any]],
    *,
    criteria: SelectionCriteria = DEFAULT_SELECTION,
    candidates: Sequence[EmitPolicy] = CANDIDATE_POLICIES,
) -> dict[str, Any]:
    ranked: list[tuple[tuple, EmitPolicy, dict[str, Any]]] = []
    for policy in candidates:
        m = validation_metrics_by_name.get(policy.name)
        if not m:
            continue
        n = int(m.get("total_trades") or 0)
        exp = float(m.get("expectancy") or 0.0)
        raw_pf = m.get("profit_factor")
        pf = float(raw_pf) if raw_pf is not None else 0.0
        qualifies = n >= criteria.min_trades and exp >= criteria.min_expectancy and pf >= criteria.min_profit_factor
        key = (0 if qualifies else 1, -exp, -pf, -n, policy.name)
        ranked.append((key, policy, m))
    ranked.sort(key=lambda x: x[0])
    if not ranked:
        return {"qualified": False, "selected": None, "reason": "no_candidate_metrics", "criteria": asdict(criteria)}
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


__all__ = [
    "BASELINE_1_4_0_TEST",
    "CANDIDATE_POLICIES",
    "DEFAULT_SELECTION",
    "DEFAULT_TEST_SUCCESS",
    "EXPERIMENT_ARM",
    "EXPERIMENT_PIPELINE_VERSION",
    "EmitPolicy",
    "evaluate_test_success",
    "filter_trades",
    "select_policy",
]

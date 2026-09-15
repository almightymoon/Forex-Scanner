"""Pipeline 1.6.0 — Arm H3 direction / alignment emit gating.

Frozen baseline analysis remains 1.4.0. This module only defines **emit gates**
on direction and structure/HTF alignment labels. No DecisionEngine weight,
ranking, zone, or SL/TP changes.

Selection and success criteria match the 1.5.0 H1 experiment contract.
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
    select_policy as _select_by_metrics,
)

EXPERIMENT_PIPELINE_VERSION = "1.6.0"
EXPERIMENT_ARM = "H3"
FROZEN_BASELINE_VERSION = "1.4.0"


def align_bias(direction: str, bias: str | None) -> str:
    """Same labels as OOS forensics (`scripts/run_oos_failure_forensics_1_4_0.py`)."""
    if not bias or bias in ("undefined", "None"):
        return "UNDEFINED"
    d = direction.lower()
    b = bias.lower()
    if b == "ranging":
        return "NEUTRAL"
    if d == "buy":
        if b == "bullish":
            return "ALIGNED"
        if b == "bearish":
            return "OPPOSED"
    if d == "sell":
        if b == "bearish":
            return "ALIGNED"
        if b == "bullish":
            return "OPPOSED"
    return "UNDEFINED"


_ALL = frozenset({"ALIGNED", "NEUTRAL", "OPPOSED", "UNDEFINED"})


@dataclass(frozen=True)
class EmitPolicy:
    """Direction + alignment emit gate."""

    name: str
    allow_buy: bool = True
    allow_sell: bool = True
    structure_allowed: frozenset[str] = field(default_factory=lambda: frozenset(_ALL))
    htf_allowed: frozenset[str] = field(default_factory=lambda: frozenset(_ALL))

    def allows(self, trade: dict[str, Any]) -> bool:
        direction = str(trade.get("direction", "")).lower()
        if direction == "buy" and not self.allow_buy:
            return False
        if direction == "sell" and not self.allow_sell:
            return False
        struct = trade.get("structure_alignment") or align_bias(
            direction, trade.get("structure_external_bias")
        )
        htf = trade.get("htf_alignment") or align_bias(
            direction, trade.get("ranking_htf_trend")
        )
        return struct in self.structure_allowed and htf in self.htf_allowed

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "allow_buy": self.allow_buy,
            "allow_sell": self.allow_sell,
            "structure_allowed": sorted(self.structure_allowed),
            "htf_allowed": sorted(self.htf_allowed),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EmitPolicy":
        return cls(
            name=data["name"],
            allow_buy=bool(data.get("allow_buy", True)),
            allow_sell=bool(data.get("allow_sell", True)),
            structure_allowed=frozenset(data.get("structure_allowed") or _ALL),
            htf_allowed=frozenset(data.get("htf_allowed") or _ALL),
        )


def _not_opposed() -> frozenset[str]:
    return frozenset({"ALIGNED", "NEUTRAL", "UNDEFINED"})


def _aligned_only() -> frozenset[str]:
    return frozenset({"ALIGNED"})


# Predeclared candidates — fixed before TRAIN/VAL metrics are used for selection.
CANDIDATE_POLICIES: tuple[EmitPolicy, ...] = (
    EmitPolicy("h3_baseline_all"),
    EmitPolicy("h3_buy_only", allow_sell=False),
    EmitPolicy("h3_sell_only", allow_buy=False),
    EmitPolicy("h3_block_structure_opposed", structure_allowed=_not_opposed()),
    EmitPolicy("h3_block_htf_opposed", htf_allowed=_not_opposed()),
    EmitPolicy("h3_structure_aligned_only", structure_allowed=_aligned_only()),
    EmitPolicy("h3_htf_aligned_only", htf_allowed=_aligned_only()),
    EmitPolicy(
        "h3_buy_block_structure_opposed",
        allow_sell=False,
        structure_allowed=_not_opposed(),
    ),
    EmitPolicy(
        "h3_buy_structure_aligned",
        allow_sell=False,
        structure_allowed=_aligned_only(),
    ),
    EmitPolicy(
        "h3_dual_aligned",
        structure_allowed=_aligned_only(),
        htf_allowed=_aligned_only(),
    ),
    EmitPolicy(
        "h3_buy_dual_aligned",
        allow_sell=False,
        structure_allowed=_aligned_only(),
        htf_allowed=_aligned_only(),
    ),
)


def annotate_alignments(trade: dict[str, Any]) -> dict[str, Any]:
    out = dict(trade)
    direction = str(out.get("direction", ""))
    out["structure_alignment"] = align_bias(direction, out.get("structure_external_bias"))
    out["htf_alignment"] = align_bias(direction, out.get("ranking_htf_trend"))
    return out


def filter_trades(
    trades: Sequence[dict[str, Any]],
    policy: EmitPolicy,
) -> list[dict[str, Any]]:
    return [t for t in trades if policy.allows(t)]


def select_policy(
    validation_metrics_by_name: dict[str, dict[str, Any]],
    *,
    criteria: SelectionCriteria = DEFAULT_SELECTION,
    candidates: Sequence[EmitPolicy] = CANDIDATE_POLICIES,
) -> dict[str, Any]:
    """Reuse H1 selection key on H3 policy names."""

    class _NameOnly:
        def __init__(self, policy: EmitPolicy):
            self.name = policy.name
            self._policy = policy

        def to_dict(self) -> dict[str, Any]:
            return self._policy.to_dict()

    wrapped = [_NameOnly(p) for p in candidates]
    result = _select_by_metrics(
        validation_metrics_by_name,
        criteria=criteria,
        candidates=wrapped,  # type: ignore[arg-type]
    )
    if result.get("selected"):
        name = result["selected"]["name"] if isinstance(result["selected"], dict) else None
        if name:
            for p in candidates:
                if p.name == name:
                    result["selected"] = p.to_dict()
                    break
    return result


def policy_by_name(name: str, candidates: Iterable[EmitPolicy] = CANDIDATE_POLICIES) -> EmitPolicy:
    for p in candidates:
        if p.name == name:
            return p
    raise KeyError(f"unknown emit policy: {name}")


__all__ = [
    "BASELINE_1_4_0_TEST",
    "CANDIDATE_POLICIES",
    "DEFAULT_SELECTION",
    "DEFAULT_TEST_SUCCESS",
    "EXPERIMENT_ARM",
    "EXPERIMENT_PIPELINE_VERSION",
    "EmitPolicy",
    "FROZEN_BASELINE_VERSION",
    "SelectionCriteria",
    "TestSuccessCriteria",
    "align_bias",
    "annotate_alignments",
    "evaluate_test_success",
    "filter_trades",
    "policy_by_name",
    "select_policy",
]

"""Structured rule checklist for Visualization Studio (Sprint 4)."""

from __future__ import annotations

from swing_engine.config import SwingEngineConfig
from swing_engine.models import (
    DetectedSwing,
    PipelineArtifacts,
    PivotCandidate,
    RejectedCandidate,
    SwingHierarchyState,
    SwingRuleCheck,
    SwingTier,
)


def build_rule_checks_for_swing(
    swing: DetectedSwing,
    artifacts: PipelineArtifacts,
    config: SwingEngineConfig,
) -> list[SwingRuleCheck]:
    """Rule pass/fail panel for an accepted or waiting swing."""
    noise_ok = _index_set(artifacts.noise_filtered)
    atr_ok = _index_set(artifacts.atr_validated)
    leg_ok = _index_set(artifacts.leg_validated)
    key = (swing.pivot_index, swing.direction.value)
    pivot = _find_pivot(artifacts.pivot_candidates, swing.pivot_index, swing.direction.value)
    leg_atr = float(swing.metadata.get("leg_atr", 0.0))
    comp = swing.metadata.get("strength_components", {})

    major_value = swing.tier.value
    major_threshold = (
        f"atr>={config.classification.major_min_atr_multiple}"
    )
    if config.classification.hierarchy_enabled:
        state = swing.hierarchy_state
        major_value = (
            f"{swing.tier.value}; hierarchy="
            f"{state.value if state is not None else 'UNKNOWN'}"
        )
        if state is SwingHierarchyState.CONFIRMED_MAJOR:
            major_value += (
                f"; reversal_atr="
                f"{float(swing.metadata.get('hierarchy_reversal_atr', 0.0)):.2f}"
            )
            major_threshold = (
                "hierarchy_reversal_atr>="
                f"{config.classification.hierarchy_reversal_atr}"
            )
        elif state is SwingHierarchyState.PROVISIONAL_MAJOR:
            major_value += (
                f"; prominence_atr="
                f"{float(swing.metadata.get('structural_prominence_atr', 0.0)):.2f}"
            )
            major_threshold = (
                "provisional_prominence_atr>="
                f"{config.classification.hierarchy_provisional_prominence_atr}"
            )
        else:
            major_threshold = (
                "confirmed/provisional recursive hierarchy major"
            )

    return [
        SwingRuleCheck(
            rule_id="pivot_detection",
            label="Pivot detected",
            passed=True,
            value=f"strength={pivot.strength:.1f}" if pivot else "n/a",
            threshold=f"min={config.pivot.min_pivot_strength}",
        ),
        SwingRuleCheck(
            rule_id="noise_filter",
            label="Noise filter",
            passed=key in noise_ok,
            value="passed" if key in noise_ok else "rejected",
        ),
        SwingRuleCheck(
            rule_id="atr_validation",
            label="ATR movement",
            passed=key in atr_ok,
            threshold=f"mult>={config.atr.validation_multiplier}",
        ),
        SwingRuleCheck(
            rule_id="leg_validation",
            label="Minimum leg",
            passed=key in leg_ok,
            value=f"leg_atr={leg_atr:.2f}",
            threshold=f"min_atr={config.leg.min_atr_multiple}",
        ),
        SwingRuleCheck(
            rule_id="confirmation",
            label="Confirmation",
            passed=swing.confirmed,
            value=f"delay={swing.confirmation_delay} bars",
            threshold=f"min_candles={config.confirmation.min_candles}",
        ),
        SwingRuleCheck(
            rule_id="major_tier",
            label="Major tier",
            passed=swing.tier == SwingTier.MAJOR,
            value=major_value,
            threshold=major_threshold,
        ),
        SwingRuleCheck(
            rule_id="quality",
            label="Quality score",
            passed=swing.quality_score >= config.quality.min_acceptable,
            value=f"{swing.quality_score:.0f}/100",
            threshold=f"min={config.quality.min_acceptable}",
        ),
        SwingRuleCheck(
            rule_id="displacement",
            label="Displacement",
            passed=float(comp.get("displacement", 0)) >= 40,
            value=f"{float(comp.get('displacement', 0)):.0f}/100",
        ),
    ]


def build_rule_checks_for_rejection(rej: RejectedCandidate) -> list[SwingRuleCheck]:
    p = rej.candidate
    return [
        SwingRuleCheck(rule_id="pivot_detection", label="Pivot detected", passed=True, value=f"@{p.price:.5f}"),
        SwingRuleCheck(
            rule_id=rej.stage,
            label=f"Failed at {rej.stage}",
            passed=False,
            value=rej.reason,
            threshold=rej.reason,
        ),
    ]


def _index_set(candidates: list[PivotCandidate]) -> set[tuple[int, str]]:
    return {(p.pivot_index, p.direction.value) for p in candidates}


def _find_pivot(candidates: list[PivotCandidate], index: int, direction: str) -> PivotCandidate | None:
    for p in candidates:
        if p.pivot_index == index and p.direction.value == direction:
            return p
    return None

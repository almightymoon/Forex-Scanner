"""Explainability (Sprint 3, Priority 3).

For every detected swing generate a structured, human-readable explanation of
*why* it was accepted, and for rejected candidates *why* they were discarded.
This makes debugging and trust in the engine much higher.

Example (accepted):
    Accepted MAJOR EXTERNAL high — quality 84/100
      • Pivot strength 0.91 (top decile)
      • Leg = 1.8x ATR (major threshold exceeded)
      • Confirmed after 3 candles
      • Swept prior high then reversed (liquidity)
"""

from __future__ import annotations

from swing_engine.config import SwingEngineConfig
from swing_engine.models import (
    DetectedSwing,
    RejectedCandidate,
    SwingExplanation,
    SwingTier,
)

_REASON_TEXT = {
    "candle_distance": "too few candles from previous pivot",
    "pip_distance": "price move below minimum pip distance",
    "atr_movement": "move too small relative to ATR",
    "min_leg": "leg below minimum length",
    "spread": "spread too wide relative to ATR",
    "volatility": "volatility below minimum threshold",
    "consolidation": "inside a consolidation window",
    "insignificant_pullback": "pullback too small to matter",
    "equal_level": "duplicate of a nearby equal level",
    "same_direction": "consecutive same-direction pivot",
    "pivot_strength": "pivot strength below minimum",
}


def build_swing_explanation(
    swing: DetectedSwing,
    config: SwingEngineConfig,
) -> SwingExplanation:
    comp = swing.metadata.get("strength_components", {})
    leg_atr = float(swing.metadata.get("leg_atr", 0.0))
    factors: list[str] = []

    factors.append(f"Pivot/strength level {swing.strength}/5 (norm {swing.normalized_score:.0f}/100)")
    factors.append(f"Leg = {leg_atr:.2f}x ATR")

    if swing.confirmed:
        factors.append(f"Confirmed after {swing.confirmation_delay} candle(s)")
    else:
        factors.append("Not yet confirmed")

    if swing.tier == SwingTier.MAJOR:
        factors.append(f"Major threshold met (>= {config.classification.major_min_atr_multiple}x ATR)")
    else:
        factors.append("Classified minor")

    factors.append(f"{swing.scope.value.title()} structure")

    disp = float(comp.get("displacement", 0.0))
    if disp >= 60:
        factors.append(f"Strong displacement ({disp:.0f}/100)")
    sweep = swing.quality_factors.get("liquidity_sweep", 0.0)
    if sweep >= 70:
        factors.append("Swept prior extreme then reversed (liquidity)")

    stage_scores = {
        "strength": float(swing.normalized_score),
        "quality": float(swing.quality_score),
        "confidence": float(swing.confidence) * 100.0,
        "leg_atr": leg_atr,
    }

    summary = (
        f"Accepted {swing.tier.value} {swing.scope.value} "
        f"{swing.direction.value.lower()} — quality {swing.quality_score:.0f}/100, "
        f"confidence {swing.confidence:.0%}"
    )

    return SwingExplanation(
        status="accepted",
        summary=summary,
        factors=factors,
        stage_scores=stage_scores,
    )


def build_rejection_explanation(rej: RejectedCandidate) -> SwingExplanation:
    reason_text = _REASON_TEXT.get(rej.reason, rej.reason)
    summary = (
        f"Rejected {rej.candidate.direction.value.lower()} @ {rej.candidate.price:.5f} "
        f"at {rej.stage} — {reason_text}"
    )
    return SwingExplanation(
        status="rejected",
        summary=summary,
        factors=[f"Stage: {rej.stage}", f"Reason: {reason_text}"],
        stage_scores={"pivot_strength": float(rej.candidate.strength)},
        rejection_stage=rej.stage,
        rejection_reason=rej.reason,
    )

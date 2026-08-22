"""Decision-time structure policy: regime gating and confluence adjustments."""

from __future__ import annotations

from dataclasses import dataclass

from shared.types.models import SMCPattern, SignalDirection, TrendDirection

from services.quant_engine.features.types import MarketFeatures
from services.quant_engine.market_structure.confluence import (
    SetupConfluenceAssessment,
    assess_setup_confluence,
)
from services.quant_engine.market_structure.regime import StructureRegime


@dataclass(frozen=True)
class StructureDecisionAdjustment:
    confidence_multiplier: float
    score_delta: int
    force_neutral: bool
    warnings: tuple[str, ...]
    reasons: tuple[str, ...]
    confluence: SetupConfluenceAssessment

    def to_dict(self) -> dict:
        return {
            "confidence_multiplier": round(self.confidence_multiplier, 3),
            "score_delta": self.score_delta,
            "force_neutral": self.force_neutral,
            "warnings": list(self.warnings),
            "reasons": list(self.reasons),
            "confluence": self.confluence.to_dict(),
        }


def apply_structure_decision_policy(
    *,
    features: MarketFeatures,
    patterns: list[SMCPattern],
    direction: SignalDirection,
    primary_trend: TrendDirection,
    mtf_trends: dict[str, TrendDirection] | None = None,
) -> StructureDecisionAdjustment:
    """Derive confidence/score adjustments from regime + setup confluence."""

    confluence = assess_setup_confluence(
        features=features,
        patterns=patterns,
        snapshot=features.structure_snapshot,
        proposed_direction=direction,
    )

    warnings: list[str] = []
    reasons: list[str] = []
    mult = 1.0
    delta = 0
    force_neutral = False

    regime = features.structure_regime

    if regime == StructureRegime.REVERSAL_PENDING.value:
        warnings.append("Structure reversal pending — reducing confidence")
        mult *= 0.82
        delta -= 3
        reasons.append("Regime reversal_pending soft penalty")
        if (
            direction is SignalDirection.BUY
            and features.external_bias is TrendDirection.BEARISH
        ) or (
            direction is SignalDirection.SELL
            and features.external_bias is TrendDirection.BULLISH
        ):
            warnings.append("Direction fights external bias during pending reversal")
            mult *= 0.9
            delta -= 2

    elif regime in (
        StructureRegime.TRENDING_BULLISH.value,
        StructureRegime.TRENDING_BEARISH.value,
    ):
        agrees = (
            (
                regime == StructureRegime.TRENDING_BULLISH.value
                and direction is SignalDirection.BUY
            )
            or (
                regime == StructureRegime.TRENDING_BEARISH.value
                and direction is SignalDirection.SELL
            )
        )
        if agrees:
            mult *= 1.06
            delta += 2
            reasons.append(f"Direction agrees with {regime}")
        elif direction in (SignalDirection.BUY, SignalDirection.SELL):
            warnings.append(f"Direction fights {regime}")
            mult *= 0.88
            delta -= 4
            reasons.append("Counter-regime trade penalty")

    elif regime == StructureRegime.RANGING.value:
        if direction in (SignalDirection.BUY, SignalDirection.SELL):
            warnings.append("Ranging structure — weaker directional edge")
            mult *= 0.92
            delta -= 1

    if confluence.aligned:
        mult *= 1.0 + min(0.08, confluence.score * 0.1)
        delta += 1 if confluence.score >= 0.7 else 0
        reasons.append(f"Setup confluence aligned ({confluence.score:.2f})")
    elif confluence.score < 0.35 and direction in (SignalDirection.BUY, SignalDirection.SELL):
        warnings.append("Low structure/setup confluence")
        mult *= 0.9
        delta -= 2
        reasons.extend(list(confluence.blockers[:2]))

    # HTF structure bias (H4/D1).
    htf_biases: list[tuple[str, TrendDirection]] = []
    for tf in ("H4", "D1"):
        t = (mtf_trends or {}).get(tf)
        if t is not None and t is not TrendDirection.RANGING:
            htf_biases.append((tf, t))
    if htf_biases and direction in (SignalDirection.BUY, SignalDirection.SELL):
        agrees_htf = 0
        fights_htf = 0
        for tf, t in htf_biases:
            if (direction is SignalDirection.BUY and t is TrendDirection.BULLISH) or (
                direction is SignalDirection.SELL and t is TrendDirection.BEARISH
            ):
                agrees_htf += 1
                reasons.append(f"{tf} structure bias aligned ({t.value})")
            else:
                fights_htf += 1
                warnings.append(f"{tf} structure bias conflicts ({t.value})")
        if agrees_htf and not fights_htf:
            mult *= 1.08
            delta += 2
            reasons.append("HTF structure bias aligned")
        elif fights_htf and not agrees_htf:
            mult *= 0.85
            delta -= 3
            reasons.append("HTF structure bias conflict")
        elif fights_htf and agrees_htf:
            mult *= 0.95
            delta -= 1
            reasons.append("Mixed HTF structure bias")

    if (
        regime == StructureRegime.REVERSAL_PENDING.value
        and confluence.score < 0.4
        and direction in (SignalDirection.BUY, SignalDirection.SELL)
        and features.external_bias is not TrendDirection.RANGING
        and (
            (direction is SignalDirection.BUY and features.external_bias is TrendDirection.BEARISH)
            or (direction is SignalDirection.SELL and features.external_bias is TrendDirection.BULLISH)
        )
    ):
        force_neutral = True
        warnings.append("Blocked: counter-bias trade during pending reversal with weak confluence")
        reasons.append("force_neutral")

    if (
        primary_trend is TrendDirection.RANGING
        and features.external_bias is not TrendDirection.RANGING
        and confluence.direction_hint is not SignalDirection.NEUTRAL
    ):
        reasons.append("Structure bias available while indicator trend ranging")

    return StructureDecisionAdjustment(
        confidence_multiplier=round(mult, 4),
        score_delta=delta,
        force_neutral=force_neutral,
        warnings=tuple(warnings),
        reasons=tuple(reasons),
        confluence=confluence,
    )

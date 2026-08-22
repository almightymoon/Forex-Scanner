"""Studio overlay helpers for StructureSnapshot → SwingVisualizer payload."""

from __future__ import annotations

from typing import Any

from services.quant_engine.market_structure.models import StructureSnapshot
from services.quant_engine.market_structure.regime import classify_structure_regime


def structure_events_for_studio(
    snapshot: StructureSnapshot,
    *,
    max_events: int = 80,
) -> list[dict[str, Any]]:
    """Map causal structure events to Lightweight Charts markers."""

    events = list(snapshot.events[-max_events:])
    out: list[dict[str, Any]] = []
    for e in events:
        bullish = e.direction.value == "bullish"
        is_choch = e.event_type.value == "CHOCH"
        out.append(
            {
                "time": e.break_timestamp.isoformat(),
                "price": e.level_price,
                "break_close": e.break_close,
                "index": e.break_index,
                "event_id": e.event_id,
                "event_type": e.event_type.value,
                "direction": e.direction.value,
                "scope": e.scope.value,
                "is_continuation": e.is_continuation,
                "level_price": e.level_price,
                "label": e.event_type.value,
                "color": (
                    "#f59e0b" if is_choch else ("#22c55e" if bullish else "#ef4444")
                ),
                "position": "aboveBar" if bullish else "belowBar",
                "shape": "circle" if is_choch else ("arrowUp" if bullish else "arrowDown"),
            }
        )
    return out


def structure_context_for_studio(snapshot: StructureSnapshot) -> dict[str, Any]:
    """Regime + bias summary for the studio sidebar."""

    assessment = classify_structure_regime(snapshot)
    return {
        "structure_regime": assessment.regime.value,
        "structure_regime_confidence": round(assessment.confidence, 3),
        "structure_regime_reasons": list(assessment.reasons),
        "external_bias": snapshot.external_bias.value,
        "pending_external_bias": snapshot.pending_external_bias.value,
        "internal_bias": snapshot.internal_bias.value,
        "pending_internal_bias": snapshot.pending_internal_bias.value,
        "event_count": len(snapshot.events),
        "latest_external_high": snapshot.latest_external_high,
        "latest_external_low": snapshot.latest_external_low,
    }


def structure_overlay_payload(snapshot: StructureSnapshot) -> dict[str, Any]:
    return {
        "structure_events": structure_events_for_studio(snapshot),
        "structure_context": structure_context_for_studio(snapshot),
    }

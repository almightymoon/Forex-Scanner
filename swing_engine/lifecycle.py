"""Swing candidate lifecycle (Sprint 4).

Explicit states let us measure repainting, support live trading, and power
replay/studio debugging:

    CANDIDATE → POSSIBLE → WAITING_CONFIRMATION → CONFIRMED → INVALIDATED
                                              ↘ REJECTED (terminal)
"""

from __future__ import annotations

from swing_engine.models import (
    DetectedSwing,
    PipelineArtifacts,
    PivotCandidate,
    RejectedCandidate,
    SwingDirection,
    SwingLifecycleEvent,
    SwingLifecycleState,
    SwingTrackedCandidate,
)


def _swing_id(pivot_index: int, direction: SwingDirection) -> str:
    return f"{direction.value}:{pivot_index}"


def build_lifecycle(
    artifacts: PipelineArtifacts,
    swings: list[DetectedSwing],
) -> list[SwingTrackedCandidate]:
    """Derive lifecycle tracks from pipeline artifacts + final swings."""
    tracks: dict[str, SwingTrackedCandidate] = {}
    swing_by_id = {_swing_id(s.pivot_index, s.direction): s for s in swings}

    for p in artifacts.pivot_candidates:
        sid = _swing_id(p.pivot_index, p.direction)
        tracks[sid] = SwingTrackedCandidate(
            swing_id=sid,
            pivot_index=p.pivot_index,
            direction=p.direction,
            price=p.price,
            state=SwingLifecycleState.CANDIDATE,
            events=[
                SwingLifecycleEvent(
                    bar_index=p.pivot_index,
                    state=SwingLifecycleState.CANDIDATE,
                    reason="pivot_detected",
                    rule_id="pivot_detection",
                )
            ],
        )

    filtered_ids = {_swing_id(p.pivot_index, p.direction) for p in artifacts.noise_filtered}
    for sid, track in list(tracks.items()):
        if sid in filtered_ids:
            track.state = SwingLifecycleState.POSSIBLE
            track.events.append(
                SwingLifecycleEvent(
                    bar_index=track.pivot_index,
                    state=SwingLifecycleState.POSSIBLE,
                    reason="passed_noise_filter",
                    rule_id="noise_filter",
                )
            )

    leg_ids = {_swing_id(p.pivot_index, p.direction) for p in artifacts.leg_validated}
    for sid, track in tracks.items():
        if sid in leg_ids and track.state != SwingLifecycleState.REJECTED:
            track.events.append(
                SwingLifecycleEvent(
                    bar_index=track.pivot_index,
                    state=SwingLifecycleState.POSSIBLE,
                    reason="passed_atr_and_leg_validation",
                    rule_id="leg_validation",
                )
            )

    for rej in _all_rejections(artifacts):
        _mark_rejected(tracks, rej)

    for internal in artifacts.unconfirmed_swings:
        sid = _swing_id(internal.pivot_index, internal.direction)
        if sid not in tracks:
            continue
        track = tracks[sid]
        if track.state == SwingLifecycleState.REJECTED:
            continue
        track.state = SwingLifecycleState.WAITING_CONFIRMATION
        track.events.append(
            SwingLifecycleEvent(
                bar_index=internal.pivot_index,
                state=SwingLifecycleState.WAITING_CONFIRMATION,
                reason="awaiting_confirmation_candles",
                rule_id="confirmation",
                metadata={"delay_so_far": internal.confirmation_delay},
            )
        )

    for internal in artifacts.confirmed_swings:
        sid = _swing_id(internal.pivot_index, internal.direction)
        if sid not in tracks:
            continue
        track = tracks[sid]
        if track.state == SwingLifecycleState.REJECTED:
            continue
        track.state = SwingLifecycleState.CONFIRMED
        track.events.append(
            SwingLifecycleEvent(
                bar_index=internal.confirmation_index or internal.pivot_index,
                state=SwingLifecycleState.CONFIRMED,
                reason="confirmation_rules_met",
                rule_id="confirmation",
                metadata={"delay": internal.confirmation_delay},
            )
        )

    for sid, swing in swing_by_id.items():
        if sid not in tracks:
            continue
        track = tracks[sid]
        track.final_swing = swing
        if swing.confirmed and track.state != SwingLifecycleState.REJECTED:
            track.state = SwingLifecycleState.CONFIRMED

    return list(tracks.values())


def compute_repainting_stats(tracks: list[SwingTrackedCandidate]) -> dict[str, float]:
    """Repainting = confirmed swings that were later invalidated (future: live updates)."""
    confirmed = [t for t in tracks if any(e.state == SwingLifecycleState.CONFIRMED for e in t.events)]
    invalidated = [t for t in tracks if t.state == SwingLifecycleState.INVALIDATED]
    waiting = [t for t in tracks if t.state == SwingLifecycleState.WAITING_CONFIRMATION]
    rejected = [t for t in tracks if t.state == SwingLifecycleState.REJECTED]
    n = len(confirmed) or 1
    return {
        "confirmed_count": float(len(confirmed)),
        "invalidated_count": float(len(invalidated)),
        "waiting_count": float(len(waiting)),
        "rejected_count": float(len(rejected)),
        "repainting_rate": len(invalidated) / n,
        "unconfirmed_rate": len(waiting) / max(len(tracks), 1),
    }


def _mark_rejected(tracks: dict[str, SwingTrackedCandidate], rej: RejectedCandidate) -> None:
    p = rej.candidate
    sid = _swing_id(p.pivot_index, p.direction)
    if sid not in tracks:
        return
    track = tracks[sid]
    track.state = SwingLifecycleState.REJECTED
    track.events.append(
        SwingLifecycleEvent(
            bar_index=p.pivot_index,
            state=SwingLifecycleState.REJECTED,
            reason=rej.reason,
            rule_id=rej.stage,
            metadata={"stage": rej.stage},
        )
    )


def _all_rejections(artifacts: PipelineArtifacts) -> list[RejectedCandidate]:
    return artifacts.noise_rejected + artifacts.atr_rejected + artifacts.leg_rejected

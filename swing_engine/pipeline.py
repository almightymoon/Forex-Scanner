"""Shared detection pipeline used by versioned engines."""

from __future__ import annotations

import subprocess
from typing import Any

from shared.types.models import Candle, Timeframe

from swing_engine.config import SwingEngineConfig, get_config
from swing_engine.confirmation import confirm_swings
from swing_engine.context import adapt_config, compute_market_context
from swing_engine.explain import build_rejection_explanation, build_swing_explanation
from swing_engine.filters import apply_noise_filters, validate_atr_movement, validate_minimum_leg
from swing_engine.hierarchy import apply_recursive_hierarchy
from swing_engine.lifecycle import build_lifecycle, compute_repainting_stats
from swing_engine.models import (
    DetectionResult,
    PipelineArtifacts,
    RejectedCandidate,
    SwingHierarchyState,
    SwingLifecycleState,
)
from swing_engine.performance import measure_performance
from swing_engine.pivots import detect_pivot_candidates
from swing_engine.rules import build_rule_checks_for_swing
from swing_engine.scoring import compute_confidence, score_and_classify
from swing_engine.structure_metadata import enrich_structure_metadata
from swing_engine.utils import compute_atr_series, log_stage


def run_pipeline(
    bars: list[Candle],
    *,
    version: str,
    symbol: str | None = None,
    timeframe: Timeframe | None = None,
    config: SwingEngineConfig | None = None,
) -> DetectionResult:
    tf = timeframe or (bars[0].timeframe if bars else Timeframe.H1)
    sym = symbol or (bars[0].symbol if bars else None)
    cfg = config or get_config(tf, version=version, symbol=sym)
    artifacts = PipelineArtifacts()
    stage_logs: list[dict[str, Any]] = []
    hierarchy_stats: dict[str, int] = {}

    if not bars:
        return DetectionResult(swings=[], symbol=symbol or "UNKNOWN", timeframe=tf, bar_count=0, version=version)

    sym = symbol or bars[0].symbol
    tf = timeframe or bars[0].timeframe

    with measure_performance(sym, tf.value, version, len(bars)) as perf_ctx:
        atr_series = compute_atr_series(bars, cfg.atr.period)
        artifacts.atr_series = atr_series

        context = compute_market_context(bars, atr_series, cfg)
        artifacts.market_context = context
        if cfg.adaptive.enabled:
            cfg = adapt_config(cfg, context)
            stage_logs.append({"stage": "adaptive", "context": context.to_dict()})

        candidates = detect_pivot_candidates(bars, cfg)
        artifacts.pivot_candidates = candidates
        stage_logs.append({"stage": "pivots", "count": len(candidates)})

        filtered, noise_rej, noise_counts = apply_noise_filters(candidates, bars, atr_series, cfg)
        artifacts.noise_filtered = filtered
        artifacts.noise_rejected = noise_rej
        stage_logs.append({"stage": "noise_filter", "count": len(filtered), "rejections": noise_counts})

        atr_valid, atr_rej = validate_atr_movement(filtered, bars, atr_series, cfg)
        artifacts.atr_validated = atr_valid
        artifacts.atr_rejected = atr_rej
        stage_logs.append({"stage": "atr_validation", "count": len(atr_valid), "rejected": len(atr_rej)})

        leg_valid, leg_rej = validate_minimum_leg(atr_valid, bars, atr_series, cfg)
        artifacts.leg_validated = leg_valid
        artifacts.leg_rejected = leg_rej
        stage_logs.append({"stage": "leg_validation", "count": len(leg_valid), "rejected": len(leg_rej)})

        confirmed = confirm_swings(leg_valid, bars, atr_series, cfg)
        artifacts.confirmed_swings = [s for s in confirmed if s.confirmed]
        artifacts.unconfirmed_swings = [s for s in confirmed if not s.confirmed]
        stage_logs.append({
            "stage": "confirmation",
            "confirmed": len(artifacts.confirmed_swings),
            "unconfirmed": len(artifacts.unconfirmed_swings),
        })

        detected = score_and_classify(confirmed, bars, atr_series, cfg)

        if cfg.classification.hierarchy_enabled:
            detected = apply_recursive_hierarchy(detected, atr_series, cfg)
            for swing in detected:
                # Tier and scope changed after first-level scoring, so refresh
                # dependent metadata rather than leaving stale explanations.
                swing.confidence = compute_confidence(swing, cfg)
                swing.explanation = build_swing_explanation(swing, cfg)

                state = (
                    swing.hierarchy_state.value
                    if swing.hierarchy_state is not None
                    else "NONE"
                )
                hierarchy_stats[state] = hierarchy_stats.get(state, 0) + 1

            stage_logs.append({
                "stage": "hierarchy",
                "count": len(detected),
                "states": dict(sorted(hierarchy_stats.items())),
            })

        if _structure_metadata_enabled(version):
            enrich_structure_metadata(detected)

        if _sprint4_enabled(version):
            artifacts.lifecycle_tracks = build_lifecycle(artifacts, detected)
            artifacts.repainting_stats = compute_repainting_stats(artifacts.lifecycle_tracks)
            track_map = {t.swing_id: t for t in artifacts.lifecycle_tracks}
            for s in detected:
                sid = f"{s.direction.value}:{s.pivot_index}"
                track = track_map.get(sid)
                s.lifecycle_state = track.state if track else (
                    SwingLifecycleState.CONFIRMED if s.confirmed else SwingLifecycleState.WAITING_CONFIRMATION
                )
                s.rule_checks = build_rule_checks_for_swing(s, artifacts, cfg)

        perf_ctx["swing_count"] = len(detected)
        stage_logs.append({"stage": "scoring", "count": len(detected)})
        stage_logs.append({"stage": "complete", "count": len(detected), "version": version})

        artifacts.decision_timeline = _build_timeline(artifacts)

    log_stage(f"{version}_complete", len(bars), len(detected), symbol=sym)

    return DetectionResult(
        swings=detected,
        symbol=sym,
        timeframe=tf,
        bar_count=len(bars),
        version=version,
        artifacts=artifacts,
        performance=perf_ctx.get("metrics"),
        stage_logs=stage_logs,
        metadata={
            "engine": "swing_engine",
            "version": version,
            "commit_hash": _git_commit_hash(),
            "adaptive": cfg.adaptive.enabled,
            "hierarchy_enabled": cfg.classification.hierarchy_enabled,
            "hierarchy_algorithm": (
                "recursive_directional_change"
                if cfg.classification.hierarchy_enabled
                else None
            ),
            "hierarchy_reversal_atr": (
                cfg.classification.hierarchy_reversal_atr
                if cfg.classification.hierarchy_enabled
                else None
            ),
            "hierarchy_provisional_prominence_atr": (
                cfg.classification.hierarchy_provisional_prominence_atr
                if cfg.classification.hierarchy_enabled
                else None
            ),
            "hierarchy_revision_stats": hierarchy_stats,
            "market_context": artifacts.market_context.to_dict() if artifacts.market_context else None,
            "repainting_stats": artifacts.repainting_stats,
        },
    )


def _sprint4_enabled(version: str) -> bool:
    return version in ("1.3.0", "1.4.0", "2.0.0", "2.1.0", "2.2.0")


def _structure_metadata_enabled(version: str) -> bool:
    return version in ("1.4.0", "2.0.0", "2.1.0", "2.2.0")


def _build_timeline(artifacts: PipelineArtifacts) -> list[dict[str, Any]]:
    timeline: list[dict[str, Any]] = []
    accepted_indices = {p.pivot_index for p in artifacts.leg_validated}

    for p in artifacts.pivot_candidates:
        entry: dict[str, Any] = {
            "pivot_index": p.pivot_index,
            "direction": p.direction.value,
            "price": p.price,
            "strength": p.strength,
            "status": "accepted" if p.pivot_index in accepted_indices else "rejected",
            "events": ["detected"],
        }
        timeline.append(entry)

    for rej in _all_rejections(artifacts):
        for entry in timeline:
            if entry["pivot_index"] == rej.candidate.pivot_index:
                entry["events"].append(f"rejected:{rej.stage}:{rej.reason}")
                entry["status"] = "rejected"
                entry["rejection_stage"] = rej.stage
                entry["rejection_reason"] = rej.reason
                entry["explanation"] = build_rejection_explanation(rej).summary

    for entry in timeline:
        if entry["status"] == "accepted":
            entry["events"].append("passed_filters")
    return timeline


def _all_rejections(artifacts: PipelineArtifacts) -> list[RejectedCandidate]:
    return artifacts.noise_rejected + artifacts.atr_rejected + artifacts.leg_rejected


def _git_commit_hash() -> str | None:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip() or None
    except (OSError, subprocess.CalledProcessError):
        return None

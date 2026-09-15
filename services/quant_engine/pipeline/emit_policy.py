"""Optional post-decision emit gate for provisional H4 policy.

Default: off. Live analysis remains frozen 1.4.0.
Enable with env ``SCANNER_EMIT_POLICY=h4_rank1_liquidity_none`` for paper/shadow only.

Does not change DecisionEngine scores — only suppresses emission (forces NEUTRAL /
clears levels) when the policy rejects the setup.
"""

from __future__ import annotations

import os
from typing import Any

from shared.types.models import ScannerSignal, SignalDirection

from services.quant_engine.pipeline.calibration_1_8_0 import EmitPolicy, CANDIDATE_POLICIES


def active_emit_policy_name() -> str | None:
    name = (os.getenv("SCANNER_EMIT_POLICY") or "").strip()
    return name or None


def resolve_emit_policy(name: str | None = None) -> EmitPolicy | None:
    key = name if name is not None else active_emit_policy_name()
    if not key:
        return None
    for p in CANDIDATE_POLICIES:
        if p.name == key:
            return p
    return None


def _trade_labels_from_signal(signal: ScannerSignal) -> dict[str, Any]:
    feats = signal.market_features or {}
    # Prefer explicit enrichment fields if a caller attached them.
    return {
        "primary_rank": feats.get("primary_rank"),
        "liquidity_relation": feats.get("liquidity_relation") or "UNKNOWN",
    }


def apply_emit_policy(
    signal: ScannerSignal,
    *,
    policy: EmitPolicy | None = None,
    labels: dict[str, Any] | None = None,
) -> ScannerSignal:
    """If policy rejects, force NEUTRAL so scanners skip the trade."""
    pol = policy if policy is not None else resolve_emit_policy()
    if pol is None:
        return signal
    row = labels if labels is not None else _trade_labels_from_signal(signal)
    if pol.allows(row):
        if signal.market_features is None:
            signal.market_features = {}
        signal.market_features["emit_policy"] = pol.name
        signal.market_features["emit_policy_passed"] = True
        return signal

    signal.direction = SignalDirection.NEUTRAL
    signal.score = min(signal.score, 49)
    if signal.market_features is None:
        signal.market_features = {}
    signal.market_features["emit_policy"] = pol.name
    signal.market_features["emit_policy_passed"] = False
    signal.warnings = list(signal.warnings or [])
    signal.warnings.append(f"emit policy {pol.name} rejected setup")
    return signal

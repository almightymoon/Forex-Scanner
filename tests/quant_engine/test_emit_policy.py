"""Tests for optional emit policy (default off = no behavior change)."""

from shared.types.models import (
    RiskLevel,
    ScannerSignal,
    ScoreBreakdown,
    SignalDirection,
    Timeframe,
    TrendDirection,
    rating_from_score,
)
from services.quant_engine.pipeline.calibration_1_8_0 import CANDIDATE_POLICIES
from services.quant_engine.pipeline.emit_policy import apply_emit_policy, resolve_emit_policy


def _sig(**feats):
    return ScannerSignal(
        symbol="XAUUSD",
        timeframe=Timeframe.H1,
        direction=SignalDirection.BUY,
        score=85,
        rating=rating_from_score(85),
        trend=TrendDirection.BULLISH,
        risk_level=RiskLevel.MEDIUM,
        score_breakdown=ScoreBreakdown(),
        market_features=dict(feats),
    )


def test_resolve_default_off(monkeypatch):
    monkeypatch.delenv("SCANNER_EMIT_POLICY", raising=False)
    assert resolve_emit_policy() is None


def test_h4_gate_rejects_sweep():
    pol = next(p for p in CANDIDATE_POLICIES if p.name == "h4_rank1_liquidity_none")
    sig = _sig(primary_rank=1, liquidity_relation="ASSOCIATED_SWEEP")
    out = apply_emit_policy(
        sig,
        policy=pol,
        labels={"primary_rank": 1, "liquidity_relation": "ASSOCIATED_SWEEP"},
    )
    assert out.direction == SignalDirection.NEUTRAL
    assert out.market_features["emit_policy_passed"] is False


def test_h4_gate_passes_none():
    pol = next(p for p in CANDIDATE_POLICIES if p.name == "h4_rank1_liquidity_none")
    sig = _sig(primary_rank=1, liquidity_relation="NONE")
    out = apply_emit_policy(
        sig,
        policy=pol,
        labels={"primary_rank": 1, "liquidity_relation": "NONE"},
    )
    assert out.direction == SignalDirection.BUY
    assert out.market_features["emit_policy_passed"] is True

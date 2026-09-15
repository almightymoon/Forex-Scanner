"""Unit tests for 1.5.0 H1 emit calibration (no OOS / no TEST peek)."""

from services.quant_engine.pipeline.calibration_1_5_0 import (
    CANDIDATE_POLICIES,
    EmitPolicy,
    evaluate_test_success,
    filter_trades,
    select_policy,
)


def test_emit_policy_band():
    p = EmitPolicy("t", min_score=71, max_score=84, max_confidence=0.84)
    assert p.allows(80, 0.7)
    assert not p.allows(90, 0.7)
    assert not p.allows(80, 0.9)


def test_filter_trades():
    trades = [
        {"score": 72, "confidence": 0.5, "r_multiple": 1.0},
        {"score": 96, "confidence": 0.9, "r_multiple": -1.0},
    ]
    p = EmitPolicy("cap84", min_score=70, max_score=84)
    out = filter_trades(trades, p)
    assert len(out) == 1
    assert out[0]["score"] == 72


def test_select_policy_prefers_qualified():
    metrics = {
        "h1_baseline_min70": {"total_trades": 100, "expectancy": -0.1, "profit_factor": 0.8},
        "h1_score_band_71_84": {"total_trades": 40, "expectancy": 0.05, "profit_factor": 1.1},
        "h1_score_cap_94": {"total_trades": 80, "expectancy": 0.02, "profit_factor": 0.9},
    }
    # Only include policies that exist in CANDIDATE_POLICIES names
    result = select_policy(metrics)
    assert result["qualified"] is True
    assert result["selected"]["name"] == "h1_score_band_71_84"


def test_select_policy_unqualified_diagnostic():
    metrics = {p.name: {"total_trades": 10, "expectancy": -0.2, "profit_factor": 0.5} for p in CANDIDATE_POLICIES}
    metrics["h1_baseline_min70"] = {"total_trades": 50, "expectancy": -0.05, "profit_factor": 0.9}
    result = select_policy(metrics)
    assert result["qualified"] is False
    assert result["selected"]["name"] == "h1_baseline_min70"


def test_evaluate_test_success():
    ok = evaluate_test_success(
        {"expectancy": 0.1, "profit_factor": 1.2, "total_r": -10.0, "total_trades": 50, "win_rate": 45}
    )
    assert ok["passed"] is True
    bad = evaluate_test_success(
        {"expectancy": -0.1, "profit_factor": 0.8, "total_r": -40.0, "total_trades": 50, "win_rate": 35}
    )
    assert bad["passed"] is False

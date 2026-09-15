"""Unit tests for 1.7.0 H2 exit geometry (no OOS / no TEST peek)."""

from services.quant_engine.pipeline.calibration_1_7_0 import (
    CANDIDATE_POLICIES,
    ExitPolicy,
    select_policy,
)


def test_baseline_keeps_levels():
    p = ExitPolicy("h2_baseline_rr_133", None)
    sl, tp = p.levels(direction="buy", entry=100.0, stop_loss=97.0, take_profit=104.0)
    assert sl == 97.0 and tp == 104.0


def test_target_rr_buy_and_sell():
    p = ExitPolicy("h2_tp_rr_2_0", 2.0)
    sl, tp = p.levels(direction="buy", entry=100.0, stop_loss=97.0, take_profit=104.0)
    assert sl == 97.0 and tp == 106.0  # risk=3, 2R=6
    sl2, tp2 = p.levels(direction="sell", entry=100.0, stop_loss=103.0, take_profit=96.0)
    assert sl2 == 103.0 and tp2 == 94.0


def test_select_prefers_qualified():
    metrics = {p.name: {"total_trades": 50, "expectancy": -0.1, "profit_factor": 0.8, "total_r": -5} for p in CANDIDATE_POLICIES}
    metrics["h2_tp_rr_2_0"] = {"total_trades": 50, "expectancy": 0.05, "profit_factor": 1.1, "total_r": 2.5}
    result = select_policy(metrics)
    assert result["qualified"] is True
    assert result["selected"]["name"] == "h2_tp_rr_2_0"

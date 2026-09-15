"""Unit tests for 1.8.0 H4 rank/liquidity gates."""

from services.quant_engine.pipeline.calibration_1_8_0 import (
    CANDIDATE_POLICIES,
    EmitPolicy,
    filter_trades,
    select_policy,
)


def test_rank1_only():
    trades = [
        {"primary_rank": 1, "liquidity_relation": "ASSOCIATED_SWEEP"},
        {"primary_rank": 2, "liquidity_relation": "NONE"},
        {"primary_rank": None, "liquidity_relation": "NONE"},
    ]
    p = next(x for x in CANDIDATE_POLICIES if x.name == "h4_rank1_only")
    out = filter_trades(trades, p)
    assert len(out) == 1 and out[0]["primary_rank"] == 1


def test_exclude_sweep():
    trades = [
        {"primary_rank": 1, "liquidity_relation": "ASSOCIATED_SWEEP"},
        {"primary_rank": 1, "liquidity_relation": "NONE"},
    ]
    p = next(x for x in CANDIDATE_POLICIES if x.name == "h4_exclude_associated_sweep")
    out = filter_trades(trades, p)
    assert len(out) == 1 and out[0]["liquidity_relation"] == "NONE"


def test_select_qualified():
    metrics = {p.name: {"total_trades": 40, "expectancy": -0.1, "profit_factor": 0.8, "total_r": -4} for p in CANDIDATE_POLICIES}
    metrics["h4_liquidity_none_only"] = {"total_trades": 25, "expectancy": 0.05, "profit_factor": 1.2, "total_r": 1.2}
    r = select_policy(metrics)
    assert r["qualified"] and r["selected"]["name"] == "h4_liquidity_none_only"

"""Unit tests for 1.6.0 H3 direction/alignment gates (no OOS / no TEST peek)."""

from services.quant_engine.pipeline.calibration_1_6_0 import (
    CANDIDATE_POLICIES,
    EmitPolicy,
    align_bias,
    annotate_alignments,
    filter_trades,
    select_policy,
)


def test_align_bias_labels():
    assert align_bias("buy", "bullish") == "ALIGNED"
    assert align_bias("buy", "bearish") == "OPPOSED"
    assert align_bias("buy", "ranging") == "NEUTRAL"
    assert align_bias("sell", "bearish") == "ALIGNED"
    assert align_bias("sell", "bullish") == "OPPOSED"


def test_buy_only_filter():
    trades = [
        annotate_alignments(
            {"direction": "buy", "structure_external_bias": "bullish", "ranking_htf_trend": "bullish", "score": 80}
        ),
        annotate_alignments(
            {"direction": "sell", "structure_external_bias": "bearish", "ranking_htf_trend": "bearish", "score": 80}
        ),
    ]
    policy = EmitPolicy("h3_buy_only", allow_sell=False)
    out = filter_trades(trades, policy)
    assert len(out) == 1
    assert out[0]["direction"] == "buy"


def test_block_structure_opposed():
    trades = [
        annotate_alignments(
            {"direction": "buy", "structure_external_bias": "bearish", "ranking_htf_trend": "bullish", "score": 80}
        ),
        annotate_alignments(
            {"direction": "buy", "structure_external_bias": "bullish", "ranking_htf_trend": "bullish", "score": 80}
        ),
    ]
    policy = next(p for p in CANDIDATE_POLICIES if p.name == "h3_block_structure_opposed")
    out = filter_trades(trades, policy)
    assert len(out) == 1
    assert out[0]["structure_alignment"] == "ALIGNED"


def test_select_prefers_qualified_buy_only():
    metrics = {p.name: {"total_trades": 30, "expectancy": -0.1, "profit_factor": 0.8} for p in CANDIDATE_POLICIES}
    metrics["h3_buy_only"] = {"total_trades": 40, "expectancy": 0.05, "profit_factor": 1.1}
    result = select_policy(metrics)
    assert result["qualified"] is True
    assert result["selected"]["name"] == "h3_buy_only"

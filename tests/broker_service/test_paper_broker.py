"""Unit tests for Phase-2-prep paper broker."""

from datetime import datetime, timezone
from pathlib import Path

from shared.types.models import (
    Candle,
    RiskLevel,
    ScannerSignal,
    ScoreBreakdown,
    SignalDirection,
    Timeframe,
    TrendDirection,
    rating_from_score,
)
from services.broker_service.paper import PaperBroker, paper_broker_enabled


def _candle(ts: str, o: float, h: float, l: float, c: float, symbol="XAUUSD") -> Candle:
    return Candle(
        symbol=symbol,
        timeframe=Timeframe.H1,
        timestamp=datetime.fromisoformat(ts.replace("Z", "+00:00")),
        open=o,
        high=h,
        low=l,
        close=c,
        volume=1,
    )


def _signal(**kwargs) -> ScannerSignal:
    base = dict(
        symbol="XAUUSD",
        timeframe=Timeframe.H1,
        direction=SignalDirection.BUY,
        score=80,
        rating=rating_from_score(80),
        trend=TrendDirection.BULLISH,
        risk_level=RiskLevel.MEDIUM,
        score_breakdown=ScoreBreakdown(),
        confidence=0.7,
        entry_zone_low=2000.0,
        entry_zone_high=2000.0,
        stop_loss=1990.0,
        take_profit_1=2020.0,
    )
    base.update(kwargs)
    return ScannerSignal(**base)


def test_paper_broker_enabled_default_off(monkeypatch):
    monkeypatch.delenv("PAPER_BROKER_ENABLED", raising=False)
    assert paper_broker_enabled() is False
    monkeypatch.setenv("PAPER_BROKER_ENABLED", "true")
    assert paper_broker_enabled() is True


def test_open_and_settle_tp(tmp_path: Path):
    broker = PaperBroker(out_dir=tmp_path, forward_bars=5)
    sig = _signal()
    order = broker.open_from_signal(
        sig,
        entry_price=2000.0,
        signal_bar_ts="2024-01-01T00:00:00+00:00",
    )
    assert order is not None
    assert order.status == "open"
    assert len(broker._open) == 1

    forward = [
        _candle("2024-01-01T01:00:00+00:00", 2001, 2005, 1995, 2002),
        _candle("2024-01-01T02:00:00+00:00", 2002, 2025, 2000, 2021),  # TP
    ]
    closed = broker.settle_with_forward(order, forward)
    assert closed is not None
    assert closed.status == "closed"
    assert closed.outcome == "win"
    assert len(broker._open) == 0
    assert broker.closed_path.exists()


def test_keep_open_until_window_or_touch(tmp_path: Path):
    broker = PaperBroker(out_dir=tmp_path, forward_bars=5)
    order = broker.open_from_signal(_signal(), entry_price=2000.0)
    assert order is not None
    # Quiet bar — no SL/TP, incomplete window → stay open
    quiet = [_candle("2024-01-01T01:00:00+00:00", 2000, 2001, 1999, 2000)]
    assert broker.settle_with_forward(order, quiet) is None
    assert order.status == "open"

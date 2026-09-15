"""Tests for live venue stubs (always refuse unless armed + implemented)."""

from services.broker_service.factory import get_broker_venue, venue_status
from services.broker_service.venue import VenueOrderRequest, venue_orders_armed


def test_venue_orders_default_off(monkeypatch):
    monkeypatch.delenv("BROKER_VENUE_ORDERS_ENABLED", raising=False)
    assert venue_orders_armed() is False


def test_oanda_refuses_when_disarmed(monkeypatch):
    monkeypatch.delenv("BROKER_VENUE_ORDERS_ENABLED", raising=False)
    monkeypatch.setenv("BROKER_VENUE", "oanda")
    monkeypatch.setenv("OANDA_API_KEY", "x")
    monkeypatch.setenv("OANDA_ACCOUNT_ID", "y")
    venue = get_broker_venue()
    result = venue.place_market_order(
        VenueOrderRequest(symbol="XAUUSD", side="buy", units=1)
    )
    assert result.status == "rejected"
    assert "BROKER_VENUE_ORDERS_ENABLED" in result.message


def test_oanda_attempts_when_armed(monkeypatch):
    monkeypatch.setenv("BROKER_VENUE_ORDERS_ENABLED", "true")
    monkeypatch.setenv("BROKER_VENUE", "oanda")
    monkeypatch.setenv("OANDA_API_KEY", "x")
    monkeypatch.setenv("OANDA_ACCOUNT_ID", "y")
    monkeypatch.setenv("OANDA_ENV", "practice")
    venue = get_broker_venue()
    result = venue.place_market_order(
        VenueOrderRequest(symbol="EURUSD", side="sell", units=1000)
    )
    # Fake credentials → HTTP reject from practice API (or network error), never silent success.
    assert result.status == "rejected"
    assert "OANDA" in result.message


def test_venue_status_shape(monkeypatch):
    monkeypatch.setenv("BROKER_VENUE", "none")
    monkeypatch.delenv("BROKER_VENUE_ORDERS_ENABLED", raising=False)
    st = venue_status()
    assert st["venue"] == "none"
    assert st["orders_armed"] is False
    assert st["ready"] is False

"""Factory for live broker venues (separate from market-data providers)."""

from __future__ import annotations

from services.broker_service.mt5_venue import MT5Venue
from services.broker_service.oanda_venue import OandaVenue
from services.broker_service.venue import BrokerVenue, selected_venue_name, venue_orders_armed


class NullVenue(BrokerVenue):
    name = "none"

    def is_ready(self) -> bool:
        return False

    def place_market_order(self, req):  # type: ignore[no-untyped-def]
        from services.broker_service.venue import VenueOrderResult

        return VenueOrderResult(
            venue=self.name,
            status="rejected",
            symbol=req.symbol,
            side=req.side,
            units=req.units,
            message="BROKER_VENUE=none — no live venue selected",
        )


def get_broker_venue(name: str | None = None) -> BrokerVenue:
    key = (name or selected_venue_name()).lower()
    if key in {"oanda", "oanda_practice"}:
        return OandaVenue()
    if key in {"mt5", "metatrader", "metatrader5"}:
        return MT5Venue()
    return NullVenue()


def venue_status() -> dict:
    venue = get_broker_venue()
    return {
        "venue": venue.name,
        "ready": venue.is_ready(),
        "orders_armed": venue_orders_armed(),
        "selected": selected_venue_name(),
    }

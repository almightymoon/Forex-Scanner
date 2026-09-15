"""MetaTrader 5 order venue stub — not armed by default."""

from __future__ import annotations

import os

from services.broker_service.venue import (
    BrokerVenue,
    VenueOrderRequest,
    VenueOrderResult,
    venue_orders_armed,
)


class MT5Venue(BrokerVenue):
    name = "mt5"

    def __init__(self) -> None:
        self._enabled = os.getenv("MT5_ENABLED", "").lower() in {"1", "true", "yes", "on"}

    def is_ready(self) -> bool:
        # Real bridge needs Windows + MetaTrader5 terminal; stub never reports ready.
        return False

    def place_market_order(self, req: VenueOrderRequest) -> VenueOrderResult:
        if not venue_orders_armed():
            return VenueOrderResult(
                venue=self.name,
                status="rejected",
                symbol=req.symbol,
                side=req.side,
                units=req.units,
                message="BROKER_VENUE_ORDERS_ENABLED is off — refusing live MT5 order",
            )
        if not self._enabled:
            return VenueOrderResult(
                venue=self.name,
                status="rejected",
                symbol=req.symbol,
                side=req.side,
                units=req.units,
                message="MT5_ENABLED is false",
            )
        return VenueOrderResult(
            venue=self.name,
            status="rejected",
            symbol=req.symbol,
            side=req.side,
            units=req.units,
            message="MT5 order bridge not implemented — configure Windows MT5 terminal first",
        )

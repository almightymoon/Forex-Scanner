"""OANDA practice/live order venue stub — not armed by default."""

from __future__ import annotations

import os

from services.broker_service.venue import (
    BrokerVenue,
    VenueOrderRequest,
    VenueOrderResult,
    venue_orders_armed,
)


class OandaVenue(BrokerVenue):
    name = "oanda"

    def __init__(self) -> None:
        self._api_key = os.getenv("OANDA_API_KEY", "")
        self._account_id = os.getenv("OANDA_ACCOUNT_ID", "")
        # Practice host by default; live host only if explicitly selected.
        env = (os.getenv("OANDA_ENV", "practice") or "practice").lower()
        self._base = (
            "https://api-fxtrade.oanda.com/v3"
            if env == "live"
            else "https://api-fxpractice.oanda.com/v3"
        )

    def is_ready(self) -> bool:
        return bool(self._api_key and self._account_id)

    def place_market_order(self, req: VenueOrderRequest) -> VenueOrderResult:
        if not venue_orders_armed():
            return VenueOrderResult(
                venue=self.name,
                status="rejected",
                symbol=req.symbol,
                side=req.side,
                units=req.units,
                message="BROKER_VENUE_ORDERS_ENABLED is off — refusing live OANDA order",
            )
        if not self.is_ready():
            return VenueOrderResult(
                venue=self.name,
                status="rejected",
                symbol=req.symbol,
                side=req.side,
                units=req.units,
                message="OANDA_API_KEY / OANDA_ACCOUNT_ID missing",
            )
        # Intentional stub: wire REST order create here when going live.
        return VenueOrderResult(
            venue=self.name,
            status="rejected",
            symbol=req.symbol,
            side=req.side,
            units=req.units,
            message=(
                f"OANDA order API not implemented yet (would POST {self._base}"
                f"/accounts/{self._account_id}/orders)"
            ),
            meta={"base_url": self._base, "account_id": self._account_id},
        )

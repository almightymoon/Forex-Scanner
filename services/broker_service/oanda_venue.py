"""OANDA practice/live order venue — REST order create when armed.

Safety:
  - BROKER_VENUE_ORDERS_ENABLED must be true
  - OANDA_API_KEY + OANDA_ACCOUNT_ID required
  - Default host is practice (api-fxpractice); live host only if OANDA_ENV=live
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from services.broker_service.venue import (
    BrokerVenue,
    VenueOrderRequest,
    VenueOrderResult,
    venue_orders_armed,
)


def _oanda_instrument(symbol: str) -> str:
    s = symbol.upper().replace("/", "").replace("_", "")
    if s == "XAUUSD":
        return "XAU_USD"
    if s == "XAGUSD":
        return "XAG_USD"
    if len(s) == 6:
        return f"{s[:3]}_{s[3:]}"
    return symbol


class OandaVenue(BrokerVenue):
    name = "oanda"

    def __init__(self) -> None:
        self._api_key = os.getenv("OANDA_API_KEY", "")
        self._account_id = os.getenv("OANDA_ACCOUNT_ID", "")
        env = (os.getenv("OANDA_ENV", "practice") or "practice").lower()
        self._env = env
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

        units = abs(float(req.units))
        if req.side == "sell":
            units = -units

        order: dict = {
            "type": "MARKET",
            "instrument": _oanda_instrument(req.symbol),
            "units": str(int(units) if units == int(units) else units),
            "timeInForce": "FOK",
            "positionFill": "DEFAULT",
        }
        if req.client_tag:
            order["clientExtensions"] = {"tag": req.client_tag[:128]}
        if req.stop_loss is not None:
            order["stopLossOnFill"] = {"price": f"{req.stop_loss:.5f}"}
        if req.take_profit is not None:
            order["takeProfitOnFill"] = {"price": f"{req.take_profit:.5f}"}

        url = f"{self._base}/accounts/{self._account_id}/orders"
        body = json.dumps({"order": order}).encode()
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept-Datetime-Format": "RFC3339",
        }
        http_req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(http_req, timeout=20) as resp:
                payload = json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode(errors="replace")[:800]
            return VenueOrderResult(
                venue=self.name,
                status="rejected",
                symbol=req.symbol,
                side=req.side,
                units=req.units,
                message=f"OANDA HTTP {exc.code}: {err_body}",
                meta={"env": self._env, "url": url},
            )
        except Exception as exc:
            return VenueOrderResult(
                venue=self.name,
                status="rejected",
                symbol=req.symbol,
                side=req.side,
                units=req.units,
                message=f"OANDA request failed: {exc}",
                meta={"env": self._env},
            )

        fill = payload.get("orderFillTransaction") or {}
        create = payload.get("orderCreateTransaction") or {}
        venue_id = str(fill.get("id") or create.get("id") or "") or None
        fill_price = None
        if fill.get("price") is not None:
            try:
                fill_price = float(fill["price"])
            except (TypeError, ValueError):
                fill_price = None

        status = "filled" if fill else "submitted"
        return VenueOrderResult(
            venue=self.name,
            status=status,
            symbol=req.symbol,
            side=req.side,
            units=req.units,
            message=f"OANDA {self._env} order {status}",
            venue_order_id=venue_id,
            fill_price=fill_price,
            meta={"env": self._env, "raw_keys": sorted(payload.keys())},
        )
